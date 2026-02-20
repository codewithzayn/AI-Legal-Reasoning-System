# How to Write Effective Prompts for the AI Legal Agent

Get better, more relevant Supreme Court (KKO) and Supreme Administrative Court (KHO) case results by following these guidelines.

---

## 1. Be Specific

**Good:** "Find KKO cases about fraud (petos) from 2015–2020"  
**Weak:** "fraud"

Specific prompts help the agent target the right legal area and time period.

---

## 2. Use Legal Terms

Include Finnish legal terms when you know them:

| Topic      | Finnish      | English   |
|-----------|--------------|-----------|
| Fraud     | petos        | fraud     |
| Theft     | varkaus      | theft     |
| Embezzlement | kavallus  | embezzlement |
| Damages   | vahingonkorvaus | damages |
| Insurance | vakuutus     | insurance |

Bilingual prompts work: *"Etsi tapauksia vahingonkorvauksesta"* or *"Find cases about damages"*.

---

## 3. Ask for a Specific Case

Use case IDs when available:

- **"Summarize KKO:2024:76"** – full summary of that case
- **"Explain KHO:2023:T97"** – focus on that decision

---

## 4. Use Follow-up Questions

The agent keeps recent context and interprets short or ambiguous follow-ups. You can:

- Ask for more on the same topic
- Switch to a related topic
- Use **"Range 2010–2020"** if asked for years — it applies that range to the last question

The agent infers what you want; no fixed phrases are required.

---

## 5. General vs Specific Queries

- **Topic search:** "Find cases about insurance contracts"
- **Question:** "What is the penalty for theft?"
- **Find cases:** "Etsi KKO-tapauksia petoksesta"

Mix and match. The agent adapts to all of these.

---

## 6. What to Avoid

- Very long questions (over 2000 characters)
- Vague prompts like "help" or "law"
- Mixing several unrelated topics in one prompt

---

## Example Prompts

| Goal                | Example Prompt                                   |
|---------------------|--------------------------------------------------|
| Fraud cases         | Find cases about fraud (petos)                   |
| Specific case       | Summarize case KKO:2024:76                       |
| Topic + years       | Insurance law cases from 2015–2020               |
| Administrative law  | Tell me about Supreme Administrative Court decisions |
| Civil courts        | Civil court jurisdiction and procedure           |
