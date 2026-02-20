# © 2026 Crest Advisory Group LLC. All rights reserved.
# PROPRIETARY AND CONFIDENTIAL
#
# Loom video script: collaborator workflow — Fork → Branch from main → PR.

**Repo:** https://github.com/codewithzayn/AI-Legal-Reasoning-System

---

## 1. Fork the repo (browser)

1. Go to **https://github.com/codewithzayn/AI-Legal-Reasoning-System**
2. Click **Fork** (top right).
3. Create fork. You now have your own copy.

---

## 2. Clone your fork (terminal)

```bash
# Replace YOUR_GITHUB_USERNAME with your GitHub username
git clone https://github.com/YOUR_GITHUB_USERNAME/AI-Legal-Reasoning-System.git
cd AI-Legal-Reasoning-System
```

---

## 3. Add original repo as upstream

```bash
git remote add upstream https://github.com/codewithzayn/AI-Legal-Reasoning-System.git
git fetch upstream
```

---

## 4. Create a branch from main

```bash
git checkout main
git pull upstream main
git checkout -b feature/short-description
```

(Use a name like `feature/eu-search` or `bugfix/citation-link` instead of `feature/short-description`.)

---

## 5. Make changes, commit, push to your fork

```bash
git add .
git commit -m "Short description of the change"
git push -u origin feature/short-description
```

---

## 6. Open a Pull Request (browser)

1. Go to **your fork** on GitHub.
2. Click **“Compare & pull request”** for the branch you just pushed.
3. **Base:** `codewithzayn/AI-Legal-Reasoning-System` → `main`
4. **Compare:** your fork → `feature/short-description`
5. Add title and description → **Create pull request**.

You do **not** merge — the owner will merge.

---

## One copy-paste block (after you’ve forked)

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/AI-Legal-Reasoning-System.git
cd AI-Legal-Reasoning-System
git remote add upstream https://github.com/codewithzayn/AI-Legal-Reasoning-System.git
git fetch upstream
git checkout main
git pull upstream main
git checkout -b feature/my-change
# ... edit files, then:
git add .
git commit -m "Describe your change"
git push -u origin feature/my-change
# Then on GitHub: Compare & pull request → Create pull request
```

Replace `YOUR_GITHUB_USERNAME` and `feature/my-change` with your username and branch name.
