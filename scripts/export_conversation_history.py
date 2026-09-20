import json
import shutil
from pathlib import Path
from datetime import datetime

conversation_id = "0cd79572-09f5-47dd-88a7-ff322d02de0f"
brain_dir = Path(r"C:\Users\jstre\.gemini\antigravity-cli\brain") / conversation_id
source_logs_dir = brain_dir / ".system_generated" / "logs"

dest_dir = Path(r"C:\Users\jstre\Projects\AnkiDeckCreator")
dest_logs_dir = dest_dir / "logs"
dest_logs_dir.mkdir(parents=True, exist_ok=True)

# Copy the raw log files (transcript.jsonl, transcript_full.jsonl)
for filename in ["transcript.jsonl", "transcript_full.jsonl"]:
    src_file = source_logs_dir / filename
    if src_file.exists():
        dest_file = dest_logs_dir / filename
        shutil.copy2(src_file, dest_file)
        print(f"Copied {filename} to {dest_file}")

# Parse transcript_full.jsonl to create human-readable CONVERSATION_HISTORY.md
transcript_file = source_logs_dir / "transcript_full.jsonl"
markdown_lines = [
    f"# Conversation History: Lecture Notes to Anki Pipeline Setup",
    f"",
    f"- **Conversation ID:** `{conversation_id}`",
    f"- **Exported On:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    f"- **Project Directory:** [`C:/Users/jstre/Projects/AnkiDeckCreator/`](file:///C:/Users/jstre/Projects/AnkiDeckCreator/)",
    f"",
    f"---",
    f""
]

if transcript_file.exists():
    with open(transcript_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            step = json.loads(line)
            step_type = step.get("type")
            created_at = step.get("created_at", "")
            content = step.get("content", "")

            if step_type == "USER_INPUT":
                markdown_lines.append(f"## 👤 User ({created_at})\n")
                markdown_lines.append(f"{content.strip()}\n")
                markdown_lines.append("---\n")
            elif step_type == "PLANNER_RESPONSE" and content:
                markdown_lines.append(f"## 🤖 Assistant ({created_at})\n")
                markdown_lines.append(f"{content.strip()}\n")
                markdown_lines.append("---\n")

history_md_path = dest_dir / "CONVERSATION_HISTORY.md"
with open(history_md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(markdown_lines))

print(f"Saved human-readable conversation history to: {history_md_path}")
