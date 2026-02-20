"""
Sidebar ingestion component for client document upload and cloud drive ingestion.
Includes OAuth connection flow, folder browser, and file picker.
"""

import streamlit as st

from src.config.logging_config import setup_logger
from src.config.translations import t

logger = setup_logger(__name__)


def render_ingestion_sidebar(lang: str, tenant_id: str | None) -> None:
    """Render the document ingestion section in the sidebar."""
    if not tenant_id:
        return

    # Restore saved connections from DB on first load
    _restore_saved_connections(tenant_id)

    st.markdown(f"**{t('ingestion_heading', lang)}**")
    st.caption(t("ingestion_tenant_label", lang, tenant=tenant_id))

    tab_upload, tab_gdrive, tab_onedrive = st.tabs(
        [
            t("ingestion_tab_upload", lang),
            t("ingestion_tab_gdrive", lang),
            t("ingestion_tab_onedrive", lang),
        ]
    )

    with tab_upload:
        _render_upload_tab(lang, tenant_id)

    with tab_gdrive:
        _render_drive_tab(lang, tenant_id, "google_drive")

    with tab_onedrive:
        _render_drive_tab(lang, tenant_id, "onedrive")

    # Show ingested documents
    _render_document_list(lang, tenant_id)

    st.markdown("---")


# ------------------------------------------------------------------
#  Connection restore
# ------------------------------------------------------------------


def _restore_saved_connections(tenant_id: str) -> None:
    """On first load, check DB for saved tokens and restore to session state."""
    if st.session_state.get("_drive_connections_restored"):
        return
    st.session_state._drive_connections_restored = True

    try:
        from src.services.drive.drive_settings import DriveSettingsService

        settings = DriveSettingsService()

        for provider, token_key, folder_key in [
            ("google_drive", "gdrive_access_token", "gdrive_folder_id"),
            ("onedrive", "onedrive_access_token", "onedrive_folder_id"),
        ]:
            if token_key not in st.session_state:
                conn = settings.get_connection(tenant_id, provider)
                if conn and conn.get("access_token"):
                    st.session_state[token_key] = conn["access_token"]
                    if conn.get("folder_id"):
                        st.session_state[folder_key] = conn["folder_id"]
    except Exception as e:
        logger.debug("Could not restore drive connections: %s", e)


# ------------------------------------------------------------------
#  Upload tab (unchanged)
# ------------------------------------------------------------------


def _render_upload_tab(lang: str, tenant_id: str) -> None:
    """File upload tab."""
    uploaded = st.file_uploader(
        t("ingestion_upload_label", lang),
        type=["pdf", "docx", "txt"],
        key="client_doc_upload",
        accept_multiple_files=False,
    )

    if uploaded and st.button(t("ingestion_ingest_btn", lang), key="ingest_upload_btn", type="primary"):
        _ingest_uploaded_file(uploaded, tenant_id, lang)


# ------------------------------------------------------------------
#  Unified drive tab (Google Drive / OneDrive)
# ------------------------------------------------------------------


def _render_drive_tab(lang: str, tenant_id: str, provider: str) -> None:
    """Render a drive tab with connect/disconnect, folder browser, and file picker."""
    import os
    from pathlib import Path

    # Check provider is configured
    if provider == "google_drive":
        client_id = os.getenv("GOOGLE_DRIVE_CLIENT_ID", "").strip()
        if not client_id:
            secret_path = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
            if not secret_path or not Path(secret_path).exists():
                st.caption(t("ingestion_gdrive_not_configured", lang))
                return
        token_key = "gdrive_access_token"
        folder_key = "gdrive_folder_id"
        connect_btn_label = t("ingestion_gdrive_connect_btn", lang)
        authorize_label = t("ingestion_gdrive_authorize", lang)
        connect_hint = t("ingestion_gdrive_connect_hint", lang)
    else:
        client_id = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
        if not client_id:
            st.caption(t("ingestion_onedrive_not_configured", lang))
            return
        token_key = "onedrive_access_token"
        folder_key = "onedrive_folder_id"
        connect_btn_label = t("ingestion_onedrive_connect_btn", lang)
        authorize_label = t("ingestion_onedrive_authorize", lang)
        connect_hint = t("ingestion_onedrive_connect_hint", lang)

    access_token = st.session_state.get(token_key)

    if not access_token:
        # --- Not connected ---
        st.caption(connect_hint)
        if st.button(connect_btn_label, key=f"{provider}_connect"):
            connector = _get_connector(provider)
            redirect_uri = _get_redirect_uri()
            auth_url = connector.get_auth_url(redirect_uri)
            st.markdown(f"[{authorize_label}]({auth_url})")
    else:
        # --- Connected ---
        col_status, col_disconnect = st.columns([2, 1])
        with col_status:
            st.caption(f"\u2705 {t('drive_connected', lang)}")
        with col_disconnect:
            if st.button(t("drive_disconnect_btn", lang), key=f"{provider}_disconnect"):
                _disconnect_drive(tenant_id, provider, token_key, folder_key)
                st.toast(t("drive_disconnect_confirm", lang))
                st.rerun()

        # Folder browser
        _render_folder_browser(lang, tenant_id, provider, access_token, folder_key)

        # File picker (uses saved folder_id if set)
        saved_folder = st.session_state.get(folder_key)
        _render_drive_file_picker(lang, tenant_id, provider, access_token, saved_folder)


# ------------------------------------------------------------------
#  Disconnect helper
# ------------------------------------------------------------------


def _disconnect_drive(tenant_id: str, provider: str, token_key: str, folder_key: str) -> None:
    """Clear drive connection from DB and session state."""
    try:
        from src.services.drive.drive_settings import DriveSettingsService

        settings = DriveSettingsService()
        settings.delete_connection(tenant_id, provider)
    except Exception as e:
        logger.error("Failed to delete connection from DB: %s", e)

    # Clear session state
    for key in [token_key, folder_key, f"{provider}_files", f"{provider}_folders", f"{provider}_breadcrumb"]:
        st.session_state.pop(key, None)


# ------------------------------------------------------------------
#  Folder browser
# ------------------------------------------------------------------


def _render_folder_browser(lang: str, tenant_id: str, provider: str, access_token: str, folder_key: str) -> None:
    """Browse folders with breadcrumb navigation and a 'Use this folder' button."""
    st.markdown(f"**{t('folder_select_heading', lang)}**")

    # Breadcrumb: list of (id, name) tuples; empty = root
    breadcrumb_key = f"{provider}_breadcrumb"
    if breadcrumb_key not in st.session_state:
        st.session_state[breadcrumb_key] = []  # root

    breadcrumb: list[tuple[str, str]] = st.session_state[breadcrumb_key]

    # Show current path
    if breadcrumb:
        path_str = " / ".join(name for _, name in breadcrumb)
        st.caption(t("folder_current", lang, folder=path_str))
    else:
        st.caption(t("folder_current", lang, folder=t("folder_root", lang)))

    # Current parent_id for listing
    current_parent = breadcrumb[-1][0] if breadcrumb else None

    # List subfolders
    folders_cache_key = f"{provider}_folders"
    # Invalidate cache when parent changes
    cached_parent_key = f"{provider}_folders_parent"
    if st.session_state.get(cached_parent_key) != current_parent:
        st.session_state.pop(folders_cache_key, None)
        st.session_state[cached_parent_key] = current_parent

    if folders_cache_key not in st.session_state:
        try:
            connector = _get_connector(provider)
            folders = connector.list_folders(access_token, current_parent)
            st.session_state[folders_cache_key] = folders
        except Exception as e:
            logger.error("Failed to list folders: %s", e)
            st.caption(t("drive_reconnect_hint", lang))
            return

    folders = st.session_state.get(folders_cache_key, [])

    # Navigation buttons row
    col_back, col_use = st.columns(2)
    with col_back:
        if breadcrumb and st.button(f"\u2b05 {t('folder_back_btn', lang)}", key=f"{provider}_folder_back"):
            st.session_state[breadcrumb_key] = breadcrumb[:-1]
            st.session_state.pop(folders_cache_key, None)
            st.session_state.pop(f"{provider}_files", None)
            st.rerun()
    with col_use:
        if st.button(t("folder_use_btn", lang), key=f"{provider}_folder_use", type="primary"):
            st.session_state[folder_key] = current_parent
            # Persist to DB
            try:
                from src.services.drive.drive_settings import DriveSettingsService

                settings = DriveSettingsService()
                settings.update_folder(tenant_id, provider, current_parent)
            except Exception as e:
                logger.error("Failed to save folder to DB: %s", e)
            # Clear file cache so it reloads with new folder
            st.session_state.pop(f"{provider}_files", None)
            st.toast(t("folder_saved", lang))
            st.rerun()

    # Subfolder list
    if folders:
        folder_names = [f["name"] for f in folders]
        selected_idx = st.selectbox(
            t("folder_select_heading", lang),
            range(len(folders)),
            format_func=lambda i: folder_names[i],
            key=f"{provider}_folder_select",
            label_visibility="collapsed",
        )
        if st.button(f"\U0001f4c2 {t('folder_open_btn', lang)}", key=f"{provider}_folder_open"):
            chosen = folders[selected_idx]
            st.session_state[breadcrumb_key] = [*breadcrumb, (chosen["id"], chosen["name"])]
            st.session_state.pop(folders_cache_key, None)
            st.session_state.pop(f"{provider}_files", None)
            st.rerun()
    else:
        st.caption(t("folder_no_subfolders", lang))


# ------------------------------------------------------------------
#  File picker
# ------------------------------------------------------------------


def _render_drive_file_picker(
    lang: str, tenant_id: str, provider: str, access_token: str, folder_id: str | None
) -> None:
    """Show file list from a connected drive folder and allow ingestion."""
    cache_key = f"{provider}_files"

    # Invalidate cache when folder changes
    cached_folder_key = f"{provider}_files_folder"
    if st.session_state.get(cached_folder_key) != folder_id:
        st.session_state.pop(cache_key, None)
        st.session_state[cached_folder_key] = folder_id

    if cache_key not in st.session_state:
        try:
            connector = _get_connector(provider)
            files = connector.list_files(access_token, folder_id)
            st.session_state[cache_key] = files
        except Exception as e:
            st.error(f"Failed to list files: {e}")
            return

    files = st.session_state.get(cache_key, [])
    if not files:
        st.caption(t("ingestion_no_files", lang))
        return

    file_names = [f"{f['name']} ({f['size'] // 1024}KB)" for f in files]
    selected_idx = st.selectbox(
        t("ingestion_select_file", lang),
        range(len(files)),
        format_func=lambda i: file_names[i],
        key=f"{provider}_file_select",
    )

    if st.button(t("ingestion_ingest_btn", lang), key=f"ingest_{provider}_btn", type="primary"):
        selected = files[selected_idx]
        _ingest_drive_file(selected, access_token, provider, tenant_id, lang)


# ------------------------------------------------------------------
#  Ingestion helpers (unchanged)
# ------------------------------------------------------------------


def _ingest_uploaded_file(uploaded, tenant_id: str, lang: str) -> None:
    """Ingest an uploaded file."""
    progress = st.progress(0, text=t("ingestion_progress_start", lang))

    def on_progress(stage: str, pct: float) -> None:
        labels = {
            "hashing": t("ingestion_progress_hashing", lang),
            "extracting": t("ingestion_progress_extracting", lang),
            "chunking": t("ingestion_progress_chunking", lang),
            "embedding": t("ingestion_progress_embedding", lang),
            "storing": t("ingestion_progress_storing", lang),
            "done": t("ingestion_progress_done", lang),
        }
        progress.progress(pct, text=labels.get(stage, stage))

    try:
        from src.services.ingestion.client_ingestion import ClientIngestionService

        service = ClientIngestionService()
        result = service.ingest_bytes(
            tenant_id=tenant_id,
            file_bytes=uploaded.getvalue(),
            filename=uploaded.name,
            source_provider="upload",
            on_progress=on_progress,
        )

        if result["status"] == "completed":
            st.success(t("ingestion_success", lang, chunks=result["chunks_count"]))
        elif result["status"] == "already_exists":
            st.info(t("ingestion_already_exists", lang))
        else:
            st.warning(t("ingestion_empty", lang))
    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        st.error(f"{t('ingestion_error', lang)}: {e}")


def _ingest_drive_file(file_info: dict, access_token: str, provider: str, tenant_id: str, lang: str) -> None:
    """Download and ingest a file from a cloud drive."""
    progress = st.progress(0, text=t("ingestion_progress_start", lang))

    def on_progress(stage: str, pct: float) -> None:
        labels = {
            "hashing": t("ingestion_progress_hashing", lang),
            "extracting": t("ingestion_progress_extracting", lang),
            "chunking": t("ingestion_progress_chunking", lang),
            "embedding": t("ingestion_progress_embedding", lang),
            "storing": t("ingestion_progress_storing", lang),
            "done": t("ingestion_progress_done", lang),
        }
        progress.progress(pct, text=labels.get(stage, stage))

    try:
        connector = _get_connector(provider)
        progress.progress(0.05, text="Downloading...")
        file_bytes = connector.download_file(access_token, file_info["id"])

        from src.services.ingestion.client_ingestion import ClientIngestionService

        service = ClientIngestionService()
        result = service.ingest_bytes(
            tenant_id=tenant_id,
            file_bytes=file_bytes,
            filename=file_info["name"],
            source_provider=provider,
            source_file_id=file_info["id"],
            on_progress=on_progress,
        )

        if result["status"] == "completed":
            st.success(t("ingestion_success", lang, chunks=result["chunks_count"]))
        elif result["status"] == "already_exists":
            st.info(t("ingestion_already_exists", lang))
        else:
            st.warning(t("ingestion_empty", lang))
    except Exception as e:
        logger.error("Drive ingestion failed: %s", e)
        st.error(f"{t('ingestion_error', lang)}: {e}")


# ------------------------------------------------------------------
#  Document list (unchanged)
# ------------------------------------------------------------------


def _render_document_list(lang: str, tenant_id: str) -> None:
    """Show list of ingested documents for this tenant."""
    try:
        from src.services.ingestion.client_ingestion import ClientIngestionService

        service = ClientIngestionService()
        docs = service.get_tenant_documents(tenant_id)
        if docs:
            with st.expander(t("ingestion_documents_heading", lang, count=len(docs)), expanded=False):
                for doc in docs[:20]:
                    status_icon = {"completed": "\u2705", "failed": "\u274c", "processing": "\u23f3"}.get(
                        doc.get("status", ""), "\u2753"
                    )
                    st.caption(f"{status_icon} {doc.get('file_name', '?')} ({doc.get('chunks_stored', 0)} chunks)")
    except Exception:
        pass  # Silently skip if table doesn't exist yet


# ------------------------------------------------------------------
#  Utilities
# ------------------------------------------------------------------


def _get_connector(provider: str):
    """Get the right drive connector for the provider."""
    if provider == "google_drive":
        from src.services.drive.google_connector import GoogleDriveConnector

        return GoogleDriveConnector()
    if provider == "onedrive":
        from src.services.drive.onedrive_connector import OneDriveConnector

        return OneDriveConnector()
    raise ValueError(f"Unknown provider: {provider}")


def _get_redirect_uri() -> str:
    """Get the redirect URI for OAuth flows (Streamlit URL)."""
    return st.session_state.get("oauth_redirect_uri", "http://localhost:8501")
