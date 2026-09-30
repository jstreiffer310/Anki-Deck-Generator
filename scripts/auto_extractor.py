import logging
from typing import List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.ollama_runtime import OllamaRuntimeManager

logger = logging.getLogger("auto_extractor")

class SyllabusDrivenExtractor:
    """
    Extracts high-yield concepts from raw lecture notes by aligning them with a syllabus.
    Acts as an automated highlighter using an LLM.
    """

    def __init__(self, runtime_manager: 'OllamaRuntimeManager'):
        """
        Args:
            runtime_manager: An initialized OllamaRuntimeManager instance.
        """
        self.runtime_manager = runtime_manager

    def _filter_syllabus_topics(self, syllabus_text: str, max_chars: int = 2500) -> str:
        """
        Condenses a lengthy syllabus to only key topical headings, weekly schedules,
        and learning objectives, stripping administrative and grading boilerplate.
        """
        if not syllabus_text:
            return ""
        
        lines = syllabus_text.split('\n')
        relevant_lines = []
        is_in_schedule = False
        
        schedule_keywords = (
            "schedule", "week", "topic", "lecture", "module", "unit", 
            "objective", "outcome", "reading", "chapter"
        )
        boilerplate_keywords = (
            "drop deadline", "withdrawal", "grading", "grade breakdown",
            "academic honesty", "cheating", "plagiarism", "office hour",
            "contact information", "zoom link", "financial deadline"
        )
        
        for line in lines:
            line_str = line.strip()
            if not line_str or len(line_str) < 3:
                continue
            line_lower = line_str.lower()
            
            if any(b in line_lower for b in boilerplate_keywords):
                continue
                
            if any(k in line_lower for k in schedule_keywords):
                is_in_schedule = True
                relevant_lines.append(line_str)
            elif is_in_schedule:
                # Keep lines following a schedule header if they look topical
                if len(line_str) < 150:
                    relevant_lines.append(line_str)
                else:
                    is_in_schedule = False

        if relevant_lines:
            condensed = "\n".join(relevant_lines)
            if len(condensed) > max_chars:
                return condensed[:max_chars]
            return condensed
            
        # Fallback: take first max_chars if no explicit schedule keyword matched
        return syllabus_text[:max_chars]

    def extract_virtual_highlights(self, syllabus_text: str, raw_notes_text: str) -> List[Dict[str, Any]]:
        """
        Chunk the raw_notes_text, prompt the LLM to extract virtual highlights 
        based on syllabus objectives, and return the combined list of extracted highlights.

        Returns a list of dictionaries, each resembling a physical highlight:
        {"heading": "...", "text": "...", "color": "yellow" | "green"}
        """
        clean_syllabus = self._filter_syllabus_topics(syllabus_text, max_chars=2500)
        chunks = self._chunk_text(raw_notes_text, max_chars=2000)
        
        all_highlights = []
        
        system_prompt = (
            "You are a highly analytical 4.0 GPA student. Your task is to extract the "
            "highest-yield concepts from lecture notes that align directly with the provided syllabus objectives.\n"
            "You must act as a precise 'auto-highlighter'. Find exact or slightly cleaned text snippets "
            "that represent core definitions, mechanisms, or contextual facts explicitly relevant to the syllabus.\n"
            "Return the output STRICTLY as a JSON object with a single key 'highlights' containing an array of objects.\n"
            "Each object MUST have exactly these keys:\n"
            "- \"heading\": A short, accurate contextual heading for the concept.\n"
            "- \"text\": The raw text snippet extracted from the notes.\n"
            "- \"color\": \"yellow\" for concepts, mechanisms, and factual claims, or \"green\" for pure definitions.\n\n"
            "Do NOT include any other keys. Do NOT include markdown blocks outside the JSON. ONLY output the JSON object."
        )

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
                
            prompt = (
                f"Syllabus Objectives / Schedule:\n{clean_syllabus or 'General Course Outline'}\n\n"
                f"Lecture Notes Snippet to Highlight:\n{chunk}\n\n"
                "Extract the virtual highlights as JSON."
            )
            
            try:
                response = self.runtime_manager.generate_json(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=0.0,  # Keep it deterministic
                    timeout=45.0
                )
                
                if response and isinstance(response, dict):
                    highlights = response.get("highlights", [])
                    if isinstance(highlights, list):
                        for hl in highlights:
                            if isinstance(hl, dict) and "heading" in hl and "text" in hl and "color" in hl:
                                if hl["color"] not in ["yellow", "green"]:
                                    hl["color"] = "yellow"
                                all_highlights.append(hl)
                            else:
                                logger.debug(f"Skipping malformed highlight from LLM: {hl}")
                    else:
                        logger.debug("Response 'highlights' key is not a list.")
                else:
                    logger.debug("Failed to get a valid JSON dict from generate_json.")
            except Exception as e:
                logger.error(f"Error extracting highlights for a chunk: {e}")
                        
        return all_highlights

    def _chunk_text(self, text: str, max_chars: int = 4000) -> List[str]:
        """
        Splits text into chunks of at most `max_chars` length, attempting to split 
        on double newlines (paragraphs) to preserve semantic boundaries.
        """
        import textwrap
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = []
        current_len = 0
        
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
                
            p_len = len(p)
            
            # If adding this paragraph exceeds max_chars, flush the current chunk
            if current_len + p_len > max_chars and current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_len = 0
                
            # If a single paragraph is longer than max_chars, subdivide it
            if p_len > max_chars:
                sub_chunks = textwrap.wrap(p, width=max_chars, break_long_words=False, replace_whitespace=False)
                for sc in sub_chunks:
                    if len(sc) > max_chars:
                        for i in range(0, len(sc), max_chars):
                            chunks.append(sc[i:i+max_chars])
                    else:
                        chunks.append(sc)
            else:
                current_chunk.append(p)
                current_len += p_len + 2  # +2 for \n\n
                
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            
        return chunks
