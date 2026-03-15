import argparse
import os
import re
import sys
import json
import html
import hashlib
import time
import urllib.request
import urllib.parse
import urllib.error
import deepl
from dotenv import load_dotenv
import tomllib

# ==========================================
# CONFIGURATION
# ==========================================

load_dotenv()
AUTH_KEY = os.getenv("DEEPL_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3-flash-preview"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

if not AUTH_KEY:
	print("Error: DEEPL_API_KEY not found in .env file.")
	print("Please create a .env file with DEEPL_API_KEY=your_key_here")
	sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
SUBMODS_DIR = os.path.join(ROOT_DIR, "submods")

BASE_LOC_PATH = os.path.join(ROOT_DIR, "main_menu", "localization")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.toml")
METADATA_PATH = os.path.join(ROOT_DIR, ".metadata", "metadata.json")
WORKSHOP_DESCRIPTION_PATH = os.path.join(ROOT_DIR, "assets", "workshop", "workshop-description.bbcode")
WORKSHOP_TRANSLATIONS_DIR = os.path.join(ROOT_DIR, "assets", "workshop", "translations")
WORKSHOP_TRANSLATION_FILENAME = "workshop_{lang}.txt"
WORKSHOP_TRANSLATION_TEMPLATE_PATH = os.path.join(WORKSHOP_TRANSLATIONS_DIR, "translation_template.txt")
WORKSHOP_TITLE_MARKER = "===WORKSHOP_TITLE==="
WORKSHOP_DESCRIPTION_MARKER = "===WORKSHOP_DESCRIPTION==="
WORKSHOP_NO_TRANSLATE_BELOW = "--NO-TRANSLATE-BELOW--"
WORKSHOP_ITEM_ID_TOKEN = "$item-id$"

ALLOWED_WORKSHOP_DESCRIPTION_TRANSLATORS = {"deepl", "gemini-3-flash"}
ALLOWED_WORKSHOP_TITLE_TRANSLATORS = {"deepl", "gemini-3-flash"}
ALLOWED_LOCALIZATION_TRANSLATORS = {"deepl", "gemini-3-flash"}

LANGUAGE_CONFIG = {
	"english": {"deepl": "EN", "loc_id": "l_english"},
	"french": {"deepl": "FR", "loc_id": "l_french"},
	"german": {"deepl": "DE", "loc_id": "l_german"},
	"spanish": {"deepl": "ES", "loc_id": "l_spanish"},
	"polish": {"deepl": "PL", "loc_id": "l_polish"},
	"russian": {"deepl": "RU", "loc_id": "l_russian"},
	"simp_chinese": {"deepl": "ZH", "loc_id": "l_simp_chinese"},
	"turkish": {"deepl": "TR", "loc_id": "l_turkish"},
	"braz_por": {"deepl": "PT", "loc_id": "l_braz_por"},
	"japanese": {"deepl": "JA", "loc_id": "l_japanese"},
	"korean": {"deepl": "KO", "loc_id": "l_korean"}
}

TARGET_LANGUAGES = {
	"english": "EN",
	"polish": "PL",
	"russian": "RU",
	"simp_chinese": "ZH",
	"spanish": "ES",
	"turkish": "TR",
	"braz_por": "PT-BR",
	"french": "FR",
	"german": "DE",
	"japanese": "JA",
	"korean": "KO"
}

LANGUAGE_DISPLAY_NAMES = {
	"english": "English",
	"polish": "Polish",
	"russian": "Russian",
	"simp_chinese": "Simplified Chinese",
	"spanish": "Spanish",
	"turkish": "Turkish",
	"braz_por": "Portuguese (Brazil)",
	"french": "French",
	"german": "German",
	"japanese": "Japanese",
	"korean": "Korean"
}

# Cache of source key/value hashes to avoid re-translating unchanged lines.
HASHES_PATH = os.path.join(SCRIPT_DIR, "dependencies", ".translate_hashes.json")
HASH_FILE_VERSION = 1

KEY_VALUE_RE = re.compile(r'^(\s*)([^:#]+):\s*"(.*)"(.*)$')
HEADER_RE = re.compile(r'^\s*l_[^:]+:\s*$')
LOCK_RE = re.compile(r'#\s*LOCK\b')
XML_PLACEHOLDER_TAG = "locvar"
DEEPL_SPLIT_SENTENCES_LOCALIZATION = deepl.api_data.SplitSentences.OFF

# ==========================================
# LOGIC
# ==========================================

def _parse_positive_int(value, label):
	"""Parse a positive integer from config values."""
	try:
		parsed = int(value)
	except (TypeError, ValueError):
		print(f"Error: {label} must be an integer.")
		return None
	if parsed <= 0:
		print(f"Error: {label} must be a positive integer.")
		return None
	return parsed

def load_config(config_path):
	"""Load config.toml and validate required keys and values."""
	invalid = (None,) * 10

	if not os.path.exists(config_path):
		print(f"Error: Config file not found: {config_path}")
		return invalid

	try:
		with open(config_path, "rb") as f:
			data = tomllib.load(f)
	except Exception as e:
		print(f"Error reading config file: {e}")
		return invalid

	source_language = data.get("source_language")
	if not source_language:
		print(f"Error: source_language not set in {config_path}")
		return invalid

	source_language = str(source_language).strip().lower()

	if source_language not in LANGUAGE_CONFIG:
		valid = ", ".join(sorted(LANGUAGE_CONFIG.keys()))
		print(f"Error: Unsupported source_language '{source_language}'.")
		print(f"Supported values: {valid}")
		return invalid

	if "localization_translator" not in data:
		print(f"Error: localization_translator not set in {config_path}")
		return invalid
	localization_translator = data.get("localization_translator")
	if not isinstance(localization_translator, str):
		print("Error: localization_translator must be a string.")
		return invalid
	if localization_translator not in ALLOWED_LOCALIZATION_TRANSLATORS:
		valid = ", ".join(sorted(ALLOWED_LOCALIZATION_TRANSLATORS))
		print(f"Error: Unsupported localization_translator '{localization_translator}'.")
		print(f"Supported values: {valid}")
		return invalid

	if "gemini_localization_system_prompt" not in data:
		print(f"Error: gemini_localization_system_prompt not set in {config_path}")
		return invalid
	gemini_localization_system_prompt = data.get("gemini_localization_system_prompt")
	if not isinstance(gemini_localization_system_prompt, str) or not gemini_localization_system_prompt.strip():
		print("Error: gemini_localization_system_prompt must be a non-empty string.")
		return invalid

	if "translate_workshop" not in data:
		print(f"Error: translate_workshop not set in {config_path}")
		return invalid
	translate_workshop = data.get("translate_workshop")
	if not isinstance(translate_workshop, bool):
		print("Error: translate_workshop must be a boolean (true/false).")
		return invalid

	if "translate_submods_by_default" not in data:
		print(f"Error: translate_submods_by_default not set in {config_path}")
		return invalid
	translate_submods_by_default = data.get("translate_submods_by_default")
	if not isinstance(translate_submods_by_default, bool):
		print("Error: translate_submods_by_default must be a boolean (true/false).")
		return invalid

	if "workshop_description_translator" not in data:
		print(f"Error: workshop_description_translator not set in {config_path}")
		return invalid
	workshop_description_translator = data.get("workshop_description_translator")
	if not isinstance(workshop_description_translator, str):
		print("Error: workshop_description_translator must be a string.")
		return invalid
	if workshop_description_translator not in ALLOWED_WORKSHOP_DESCRIPTION_TRANSLATORS:
		valid = ", ".join(sorted(ALLOWED_WORKSHOP_DESCRIPTION_TRANSLATORS))
		print(f"Error: Unsupported workshop_description_translator '{workshop_description_translator}'.")
		print(f"Supported values: {valid}")
		return invalid

	if "workshop_title_translator" not in data:
		print(f"Error: workshop_title_translator not set in {config_path}")
		return invalid
	workshop_title_translator = data.get("workshop_title_translator")
	if not isinstance(workshop_title_translator, str):
		print("Error: workshop_title_translator must be a string.")
		return invalid
	if workshop_title_translator not in ALLOWED_WORKSHOP_TITLE_TRANSLATORS:
		valid = ", ".join(sorted(ALLOWED_WORKSHOP_TITLE_TRANSLATORS))
		print(f"Error: Unsupported workshop_title_translator '{workshop_title_translator}'.")
		print(f"Supported values: {valid}")
		return invalid

	if "gemini_description_system_prompt" not in data:
		print(f"Error: gemini_description_system_prompt not set in {config_path}")
		return invalid
	gemini_description_system_prompt = data.get("gemini_description_system_prompt")
	if not isinstance(gemini_description_system_prompt, str) or not gemini_description_system_prompt.strip():
		print("Error: gemini_description_system_prompt must be a non-empty string.")
		return invalid

	if "gemini_title_system_prompt" not in data:
		print(f"Error: gemini_title_system_prompt not set in {config_path}")
		return invalid
	gemini_title_system_prompt = data.get("gemini_title_system_prompt")
	if not isinstance(gemini_title_system_prompt, str) or not gemini_title_system_prompt.strip():
		print("Error: gemini_title_system_prompt must be a non-empty string.")
		return invalid

	workshop_item_id = None
	if translate_workshop:
		if "workshop_upload_item_id" not in data:
			print(f"Error: workshop_upload_item_id not set in {config_path}")
			return invalid
		workshop_item_id = _parse_positive_int(
			data.get("workshop_upload_item_id"),
			"workshop_upload_item_id"
		)
		if workshop_item_id is None:
			return invalid

	return (
		source_language,
		translate_workshop,
		translate_submods_by_default,
		localization_translator,
		gemini_localization_system_prompt,
		workshop_description_translator,
		gemini_description_system_prompt,
		workshop_title_translator,
		gemini_title_system_prompt,
		workshop_item_id
	)

def parse_args():
	"""Parse command line arguments."""
	parser = argparse.ArgumentParser(
		description="Translate localization and optional workshop text."
	)
	parser.add_argument(
		"--submods",
		action="store_true",
		help="Also process all submods under submods/* (overrides translate_submods_by_default for this run)."
	)
	return parser.parse_args()

def build_translation_targets(include_submods):
	"""Build translation targets for the main mod and optional submods."""
	targets = [
		{
			"cache_key": "main",
			"log_prefix": "",
			"loc_base_path": BASE_LOC_PATH,
			"metadata_path": METADATA_PATH,
			"workshop_description_path": WORKSHOP_DESCRIPTION_PATH,
			"workshop_translations_dir": WORKSHOP_TRANSLATIONS_DIR,
			"workshop_template_path": WORKSHOP_TRANSLATION_TEMPLATE_PATH
		}
	]

	if not include_submods:
		return targets

	if not os.path.isdir(SUBMODS_DIR):
		print(f"Warning: --submods specified, but directory not found: {SUBMODS_DIR}")
		return targets

	for entry in sorted(os.scandir(SUBMODS_DIR), key=lambda e: e.name.lower()):
		if not entry.is_dir():
			continue
		submod_root = entry.path
		workshop_dir = os.path.join(submod_root, "workshop")
		translations_dir = os.path.join(workshop_dir, "translations")
		targets.append(
			{
				"cache_key": entry.name,
				"log_prefix": f"[submods/{entry.name}] ",
				"loc_base_path": os.path.join(submod_root, "main_menu", "localization"),
				"metadata_path": os.path.join(submod_root, ".metadata", "metadata.json"),
				"workshop_description_path": os.path.join(workshop_dir, "workshop-description.bbcode"),
				"workshop_translations_dir": translations_dir,
				"workshop_template_path": os.path.join(translations_dir, "translation_template.txt")
			}
		)

	return targets

def get_cache_bucket(hash_data, cache_key):
	"""Return the hash/cache bucket for the main mod or a specific submod."""
	if cache_key == "main":
		files = hash_data.setdefault("files", {})
		if not isinstance(files, dict):
			hash_data["files"] = {}
		return hash_data

	submods_cache = hash_data.setdefault("submods", {})
	if not isinstance(submods_cache, dict):
		submods_cache = {}
		hash_data["submods"] = submods_cache

	cache_bucket = submods_cache.setdefault(cache_key, {})
	if not isinstance(cache_bucket, dict):
		cache_bucket = {}
		submods_cache[cache_key] = cache_bucket

	files = cache_bucket.setdefault("files", {})
	if not isinstance(files, dict):
		cache_bucket["files"] = {}

	return cache_bucket

def get_translator():
	"""Create a DeepL Translator instance."""
	try:
		return deepl.Translator(AUTH_KEY)
	except Exception as e:
		print(f"Error initializing DeepL: {e}")
		return None

def load_hashes(path):
	"""
	Load the per-file, per-key hash cache. If missing or invalid, rebuild cleanly.
	"""
	if not os.path.exists(path):
		return {"version": HASH_FILE_VERSION, "files": {}}

	try:
		with open(path, "r", encoding="utf-8") as f:
			data = json.load(f)
		if not isinstance(data, dict):
			raise ValueError("Hash file must be a JSON object.")
		if data.get("version") != HASH_FILE_VERSION:
			raise ValueError("Unsupported hash file version.")
		files = data.get("files")
		if not isinstance(files, dict):
			raise ValueError("Hash file 'files' must be a JSON object.")
		return data
	except Exception as e:
		print(f"Warning: Failed to read hash file '{path}': {e}. Rebuilding.")
		return {"version": HASH_FILE_VERSION, "files": {}}

def save_hashes(path, data):
	"""
	Atomically persist the hash cache to disk.
	"""
	os.makedirs(os.path.dirname(path), exist_ok=True)
	tmp_path = path + ".tmp"
	with open(tmp_path, "w", encoding="utf-8") as f:
		json.dump(data, f, indent=2, sort_keys=True)
	os.replace(tmp_path, path)

def hash_text(text):
	"""
	Stable hash of the source value to detect changes.
	"""
	return hashlib.sha256(text.encode("utf-8")).hexdigest()

def mask_text_var(text):
	"""
	Replaces blocks with [VAR_0], [VAR_1], etc to prevent DeepL from breaking it.
	"""
	placeholders = []

	def replace_match(match):
		idx = len(placeholders)
		placeholders.append(match.group(0))
		return f'[VAR_{idx}]'

	# Single pass prevents already-masked [VAR_x] tokens from being re-masked.
	pattern = re.compile(
		r'(\\n|\[.*?\]|\$.*?\$|@[a-zA-Z0-9_]+!?|#[a-zA-Z0-9_]+|#!)'
	)
	text = pattern.sub(replace_match, text)

	return text, placeholders

def escape_xml(text):
	"""Escape XML special chars so DeepL XML tag handling stays valid."""
	return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def unescape_xml(text):
	"""Reverse escape_xml using standard HTML entity unescape."""
	return html.unescape(text)

def mask_text_var_xml_from_masked(masked_text, placeholders):
	"""Convert [VAR_x] placeholders into XML tags for DeepL tag handling."""
	escaped = escape_xml(masked_text)
	def replace_match(match):
		try:
			idx = int(match.group(1))
			placeholder_text = placeholders[idx]
		except (ValueError, IndexError):
			placeholder_text = match.group(0)
		return f'<{XML_PLACEHOLDER_TAG} id="{match.group(1)}">{escape_xml(placeholder_text)}</{XML_PLACEHOLDER_TAG}>'
	return re.sub(r'\[VAR_(\d+)\]', replace_match, escaped)

def unmask_text_var(text, placeholders):
	"""
	Restores [VAR_0] -> Original Text.
	"""
	def restore_match(match):
		try:
			idx = int(match.group(1))
			if 0 <= idx < len(placeholders):
				return placeholders[idx]
		except ValueError:
			pass
		return match.group(0)

	# Regex matches: Optional [, whitespace, VAR_, Digit, whitespace, Optional ]
	return re.sub(r'\[?\s*VAR_(\d+)\s*\]?', restore_match, text)

def unmask_text_var_xml(text, placeholders):
	"""
	Restores <locvar id="0">...</locvar> -> Original Text.
	"""
	def restore_match(match):
		try:
			idx = int(match.group(1))
			if 0 <= idx < len(placeholders):
				return placeholders[idx]
		except ValueError:
			pass
		return match.group(0)

	# Replace paired tags with or without content.
	text = re.sub(
		rf'<{XML_PLACEHOLDER_TAG}\s+id=[\'"](\d+)[\'"]\s*>.*?</{XML_PLACEHOLDER_TAG}\s*>',
		restore_match,
		text,
		flags=re.DOTALL
	)
	# Replace self-closing tags.
	return re.sub(
		rf'<{XML_PLACEHOLDER_TAG}\s+id=[\'"](\d+)[\'"]\s*/\s*>',
		restore_match,
		text
	)

def normalize_localization_linebreaks(text):
	"""Convert raw line breaks to escaped \\n for single-line localization values."""
	text = text.replace("\r\n", "\n").replace("\r", "\n")
	return text.replace("\n", r"\n")

def missing_placeholder_indices(translated_text, placeholders):
	"""Return indices of placeholders missing from translated_text (VAR or XML-tagged)."""
	found_set = set(int(x) for x in re.findall(r'VAR_(\d+)', translated_text))
	found_set.update(
		int(x)
		for x in re.findall(rf'<{XML_PLACEHOLDER_TAG}\s+id=[\'"](\d+)[\'"]', translated_text)
	)

	missing = []
	for i, placeholder in enumerate(placeholders):
		if i in found_set:
			continue
		if placeholder == r"\n" and "\n" in translated_text:
			continue
		if placeholder and placeholder in translated_text:
			continue
		missing.append(i)
	return missing

def insert_missing_placeholders(text, placeholders, missing_indices):
	"""Append missing placeholders, keeping punctuation at the end if possible."""
	if not missing_indices:
		return text
	missing_tokens = [placeholders[i] for i in missing_indices]
	suffix = "".join(missing_tokens)
	if not text:
		return suffix

	match = re.search(r'([.!?。！？])\s*$', text)
	if match:
		# Keep sentence-ending punctuation last to avoid odd UI output.
		idx = match.start(1)
		return text[:idx] + suffix + text[idx:]
	return text + suffix

def translate_deepl_xml(translator, masked_text, placeholders, deepl_code, source_lang_deepl, split_sentences):
	"""Translate masked text using XML tag handling."""
	masked_xml = mask_text_var_xml_from_masked(masked_text, placeholders)
	result = translator.translate_text(
		masked_xml,
		target_lang=deepl_code,
		source_lang=source_lang_deepl,
		tag_handling="xml",
		non_splitting_tags=[XML_PLACEHOLDER_TAG],
		ignore_tags=[XML_PLACEHOLDER_TAG],
		split_sentences=split_sentences,
		preserve_formatting=True
	)
	translated_raw = normalize_localization_linebreaks(unescape_xml(result.text))
	missing = missing_placeholder_indices(translated_raw, placeholders)
	translated_text = unmask_text_var_xml(translated_raw, placeholders)
	translated_text = unmask_text_var(translated_text, placeholders)
	return translated_text, missing

def translate_deepl_plain(translator, masked_text, placeholders, deepl_code, source_lang_deepl, split_sentences):
	"""Translate masked text without XML tag handling."""
	result = translator.translate_text(
		masked_text,
		target_lang=deepl_code,
		source_lang=source_lang_deepl,
		split_sentences=split_sentences,
		preserve_formatting=True
	)
	translated_raw = normalize_localization_linebreaks(result.text)
	missing = missing_placeholder_indices(translated_raw, placeholders)
	translated_text = unmask_text_var(translated_raw, placeholders)
	return translated_text, missing

def validate_translation(translated_text, placeholders):
	"""
	Checks if DeepL dropped any tags.
	"""
	missing_indices = missing_placeholder_indices(translated_text, placeholders)

	if missing_indices:
		missing_tags = [placeholders[i] for i in missing_indices]
		return False, f"Missing tags: {missing_tags}"

	return True, "OK"

def cleanup_text(text):
	"""
	Cleans up common AI formatting errors.
	"""
	text = re.sub(r'\s+([,.])', r'\1', text) # Fix space before punctuation
	text = re.sub(r' +', ' ', text)          # Fix double spaces
	text = text.replace('[[', '[').replace(']]', ']') # Fix double brackets
	return text.strip()

def should_auto_skip(masked_text):
	"""
	Returns True if the line should be skipped.
	Conditions:
	1. Line is empty or whitespace.
	2. Line consists only of placeholders and punctuation (e.g., "[VAR_0]").
	"""
	# 1. Check for empty/whitespace only
	if not masked_text.strip():
		return True

	# 2. Remove all [VAR_x] tags
	stripped = re.sub(r'\[VAR_\d+\]', '', masked_text)

	# 3. Remove standard punctuation and whitespace
	stripped = re.sub(r'[ \t\.,!?:;]', '', stripped)

	# If nothing is left, it was only placeholders/punctuation
	return len(stripped) == 0

def parse_source_entries(lines):
	"""
	Parse all translatable key/value entries with NO-TRANSLATE flags.
	"""
	entries = []
	ignore_block_active = False

	for line in lines:
		if "# NO-TRANSLATE BELOW" in line:
			ignore_block_active = True
		if "# NO-TRANSLATE END" in line:
			ignore_block_active = False

		no_translate = ignore_block_active or ("# NO-TRANSLATE" in line)

		match = KEY_VALUE_RE.match(line)
		if match:
			indent = match.group(1)
			key = match.group(2)
			original_value = match.group(3)
			comment = match.group(4) if match.group(4) else ""
			entries.append({
				"indent": indent,
				"key": key,
				"value": original_value,
				"comment": comment,
				"no_translate": no_translate
			})

	return entries

def translate_localization_value_gemini(
	masked_text,
	placeholders,
	target_language,
	key,
	target_folder_name,
	system_prompt
):
	"""Translate a single localization value using Gemini."""
	prompt = _build_gemini_system_prompt(system_prompt, target_language)
	payload = {
		"systemInstruction": {"parts": [{"text": prompt}]},
		"contents": [
			{"role": "user", "parts": [{"text": masked_text}]}
		]
	}

	response = _gemini_generate_content(payload)
	if response is None:
		return None

	translated_text = _gemini_extract_text(response)
	if translated_text is None:
		print("  [Error] Gemini API returned no text.")
		return None

	translated_text = normalize_localization_linebreaks(translated_text)
	missing = missing_placeholder_indices(translated_text, placeholders)
	if missing:
		missing_tags = [placeholders[i] for i in missing]
		print(f"  [WARNING] {target_folder_name} issue in '{key}': Missing tags: {missing_tags}")
		translated_text = insert_missing_placeholders(translated_text, placeholders, missing)

	translated_text = unmask_text_var(translated_text, placeholders)
	return cleanup_text(translated_text)

def translate_value(
	translator,
	key,
	original_value,
	deepl_code,
	source_lang_deepl,
	target_folder_name,
	no_translate,
	localization_translator,
	gemini_localization_system_prompt
):
	"""
	Translate a single value with tag masking and validation.
	"""
	if no_translate:
		return original_value

	masked_text, placeholders = mask_text_var(original_value)

	if should_auto_skip(masked_text):
		return original_value

	if localization_translator == "gemini-3-flash":
		target_language = LANGUAGE_DISPLAY_NAMES.get(target_folder_name, target_folder_name)
		translated_text = translate_localization_value_gemini(
			masked_text,
			placeholders,
			target_language,
			key,
			target_folder_name,
			gemini_localization_system_prompt
		)
		if translated_text is None:
			print(f"  [Error] Failed to translate line: {key} (Gemini request failed)")
			return original_value
		return translated_text

	try:
		split_sentences = DEEPL_SPLIT_SENTENCES_LOCALIZATION if placeholders else None

		translated_text, missing_xml = translate_deepl_xml(
			translator,
			masked_text,
			placeholders,
			deepl_code,
			source_lang_deepl,
			split_sentences
		)

		translated_plain = None
		missing_plain = None
		if missing_xml:
			translated_plain, missing_plain = translate_deepl_plain(
				translator,
				masked_text,
				placeholders,
				deepl_code,
				source_lang_deepl,
				split_sentences
			)

		# Choose the translation that preserves more placeholders.
		if missing_plain is not None and len(missing_plain) < len(missing_xml):
			translated_text = translated_plain
			missing = missing_plain
		else:
			missing = missing_xml

		if missing:
			missing_tags = [placeholders[i] for i in missing]
			print(f"  [WARNING] {target_folder_name} issue in '{key}': Missing tags: {missing_tags}")
			# If the engine drops tags, reinsert them rather than falling back to English.
			translated_text = insert_missing_placeholders(translated_text, placeholders, missing)

		translated_text = cleanup_text(translated_text)
		return translated_text

	except Exception as e:
		print(f"  [Error] Failed to translate line: {key} ({e})")
		return original_value

def build_line(indent, key, text, comment):
	"""Format a localization key/value line with optional comment."""
	return f'{indent}{key}: "{text}"{comment}\n'

def is_locked_line(line):
	"""
	Detect a # LOCK comment on an output line to prevent overwrites.
	"""
	match = KEY_VALUE_RE.match(line)
	if not match:
		return False
	comment = match.group(4) if match.group(4) else ""
	return bool(LOCK_RE.search(comment))

def ensure_target_header(target_lines, new_lang_id):
	"""
	Ensure the localization header matches the target language.
	"""
	for i, line in enumerate(target_lines):
		if HEADER_RE.match(line.strip()):
			if line.strip() != f"{new_lang_id}:":
				target_lines[i] = f"{new_lang_id}:\n"
				return True
			return False
	return False

def build_target_key_index(lines):
	"""
	Build a key->line index for fast in-place updates.
	"""
	index = {}
	for i, line in enumerate(lines):
		match = KEY_VALUE_RE.match(line)
		if match:
			index[match.group(2)] = i
	return index

def prune_target_lines(target_lines, source_keys):
	"""Remove translated lines whose keys no longer exist in the source."""
	new_lines = []
	removed_count = 0
	for line in target_lines:
		match = KEY_VALUE_RE.match(line)
		if match and match.group(2) not in source_keys:
			removed_count += 1
			continue
		new_lines.append(line)
	return new_lines, removed_count

def update_target_lines(
	translator,
	target_lines,
	source_entries,
	changed_keys,
	deepl_code,
	source_lang_deepl,
	target_folder_name,
	localization_translator,
	gemini_localization_system_prompt
):
	"""
	Update only keys that changed in the source (or are missing in the target).
	"""
	target_index = build_target_key_index(target_lines)
	file_changed = False

	for entry in source_entries:
		key = entry["key"]

		needs_update = key in changed_keys or key not in target_index
		if not needs_update:
			continue

		translated_text = translate_value(
			translator,
			key,
			entry["value"],
			deepl_code,
			source_lang_deepl,
			target_folder_name,
			entry["no_translate"],
			localization_translator,
			gemini_localization_system_prompt
		)

		if key in target_index:
			line_index = target_index[key]
			existing_line = target_lines[line_index]
			if is_locked_line(existing_line):
				continue
			match = KEY_VALUE_RE.match(existing_line)
			if match:
				indent = match.group(1)
				comment = match.group(4) if match.group(4) else ""
				new_line = build_line(indent, key, translated_text, comment)
			else:
				new_line = build_line(entry["indent"], key, translated_text, entry["comment"])

			if new_line != existing_line:
				target_lines[line_index] = new_line
				file_changed = True
		else:
			new_line = build_line(entry["indent"], key, translated_text, entry["comment"])
			if target_lines and not target_lines[-1].endswith("\n"):
				target_lines[-1] = target_lines[-1] + "\n"
			target_lines.append(new_line)
			target_index[key] = len(target_lines) - 1
			file_changed = True

	return file_changed

def translate_source_lines(
	translator,
	source_lines,
	target_folder_name,
	deepl_code,
	source_lang_id,
	source_lang_deepl,
	localization_translator,
	gemini_localization_system_prompt
):
	"""
	Translate a full source file into a new target file.
	"""
	new_lang_id = f"l_{target_folder_name}"
	new_lines = []
	ignore_block_active = False

	for line in source_lines:
		stripped_line = line.strip()

		# 1. Handle Language Header
		if stripped_line.startswith(f"{source_lang_id}:"):
			new_lines.append(f"{new_lang_id}:\n")
			continue

		# 2. Check for ignored lines
		if "# NO-TRANSLATE BELOW" in line:
			ignore_block_active = True
			new_lines.append(line)
			continue

		if "# NO-TRANSLATE END" in line:
			ignore_block_active = False
			new_lines.append(line)
			continue

		if ignore_block_active:
			new_lines.append(line)
			continue

		if "# NO-TRANSLATE" in line:
			new_lines.append(line)
			continue

		# 3. Parse Key-Value Pairs
		match = KEY_VALUE_RE.match(line)

		if match:
			indent = match.group(1)
			key = match.group(2)
			original_value = match.group(3)
			comment = match.group(4) if match.group(4) else ""

			translated_text = translate_value(
				translator,
				key,
				original_value,
				deepl_code,
				source_lang_deepl,
				target_folder_name,
				False,
				localization_translator,
				gemini_localization_system_prompt
			)

			new_lines.append(build_line(indent, key, translated_text, comment))
		else:
			# Copy comments / whitespace lines
			new_lines.append(line)

	return new_lines

def process_file(
	translator,
	source_lines,
	source_entries,
	source_filepath,
	loc_base_path,
	target_folder_name,
	deepl_code,
	source_lang_id,
	source_lang_deepl,
	changed_keys,
	localization_translator,
	gemini_localization_system_prompt,
	log_prefix
):
	"""Translate/update one localization file for a single target language."""
	filename = os.path.basename(source_filepath)
	new_lang_id = f"l_{target_folder_name}"
	if source_lang_id in filename:
		new_filename = filename.replace(source_lang_id, new_lang_id)
	else:
		new_filename = filename

	target_dir = os.path.join(loc_base_path, target_folder_name)
	os.makedirs(target_dir, exist_ok=True)
	target_filepath = os.path.join(target_dir, new_filename)

	# If the target doesn't exist yet, write a fully translated file.
	if not os.path.exists(target_filepath):
		print(f"{log_prefix}Translating {filename} -> {target_folder_name}...")
		new_lines = translate_source_lines(
			translator,
			source_lines,
			target_folder_name,
			deepl_code,
			source_lang_id,
			source_lang_deepl,
			localization_translator,
			gemini_localization_system_prompt
		)
		with open(target_filepath, 'w', encoding='utf-8-sig') as f:
			f.writelines(new_lines)
		return

	with open(target_filepath, 'r', encoding='utf-8-sig') as f:
		target_lines = f.readlines()

	target_index = build_target_key_index(target_lines)
	source_keys = {entry["key"] for entry in source_entries}
	has_missing_keys = any(entry["key"] not in target_index for entry in source_entries)
	has_removed_keys = any(key not in source_keys for key in target_index)
	header_needs_update = False
	for line in target_lines:
		if HEADER_RE.match(line.strip()):
			header_needs_update = line.strip() != f"{new_lang_id}:"
			break

	# Skip work if nothing changed and the header matches.
	if not changed_keys and not has_missing_keys and not has_removed_keys and not header_needs_update:
		print(f"{log_prefix}No changes for {filename} -> {target_folder_name}; skipping.")
		return

	print(f"{log_prefix}Translating {filename} -> {target_folder_name}...")

	# Update only changed or missing keys; preserve everything else.
	file_changed = ensure_target_header(target_lines, new_lang_id)
	if has_removed_keys:
		target_lines, removed_count = prune_target_lines(target_lines, source_keys)
		if removed_count:
			file_changed = True
			print(f"{log_prefix}  Removed {removed_count} obsolete keys from {filename} -> {target_folder_name}.")
	file_changed = update_target_lines(
		translator,
		target_lines,
		source_entries,
		changed_keys,
		deepl_code,
		source_lang_deepl,
		target_folder_name,
		localization_translator,
		gemini_localization_system_prompt
	) or file_changed

	if file_changed:
		with open(target_filepath, 'w', encoding='utf-8-sig') as f:
			f.writelines(target_lines)
	else:
		print(f"{log_prefix}No output changes for {filename} -> {target_folder_name}.")

def _remove_dev_suffix(name):
	"""Strip a trailing ' Dev' suffix from a mod name."""
	if name.endswith(" Dev"):
		return name[:-4].rstrip()
	return name.strip()

def load_workshop_title(metadata_path):
	"""Load the workshop title from metadata.json and remove dev suffix."""
	if not os.path.exists(metadata_path):
		return None
	try:
		with open(metadata_path, "r", encoding="utf-8-sig") as f:
			data = json.load(f)
	except Exception as e:
		print(f"Warning: Failed to read metadata file '{metadata_path}': {e}")
		return None

	title = data.get("name")
	if not title:
		print(f"Warning: Metadata 'name' not found in {metadata_path}")
		return None

	return _remove_dev_suffix(str(title))

def load_workshop_description(description_path):
	"""Read the workshop description source text."""
	if not os.path.exists(description_path):
		return None
	try:
		with open(description_path, "r", encoding="utf-8-sig") as f:
			return f.read()
	except Exception as e:
		print(f"Warning: Failed to read workshop description '{description_path}': {e}")
		return None

def split_workshop_description(text):
	"""Split workshop description into translatable and source variants."""
	if text is None:
		return None, None
	lines = text.splitlines(keepends=True)
	for idx, line in enumerate(lines):
		if line.strip() == WORKSHOP_NO_TRANSLATE_BELOW:
			translatable = "".join(lines[:idx])
			source_text = "".join(lines[:idx] + lines[idx + 1:])
			return translatable, source_text
	return text, text

def apply_workshop_item_id(text, item_id):
	"""Replace the $item-id$ token when an item id is available."""
	if text is None or item_id is None:
		return text
	return text.replace(WORKSHOP_ITEM_ID_TOKEN, str(item_id))

def build_workshop_translation_text(title, description):
	"""Build the combined workshop translation file content."""
	parts = []
	if title is not None:
		parts.append(f"{WORKSHOP_TITLE_MARKER}\n{title}\n")
	if description is not None:
		parts.append(f"{WORKSHOP_DESCRIPTION_MARKER}\n{description}")
	return "".join(parts)

def load_workshop_translation_template(template_path):
	"""Load the translation template text if present and valid."""
	if not os.path.exists(template_path):
		return None
	try:
		with open(template_path, "r", encoding="utf-8") as f:
			template = f.read()
	except Exception as e:
		print(f"Warning: Failed to read workshop translation template '{template_path}': {e}")
		return None

	if WORKSHOP_TITLE_MARKER not in template or WORKSHOP_DESCRIPTION_MARKER not in template:
		print(f"Warning: Workshop translation template '{template_path}' is missing required markers; ignoring it.")
		return None

	return template

def resolve_workshop_translation_template(primary_template_path, fallback_template_path):
	"""Load workshop template, falling back to fallback_template_path when needed."""
	template = load_workshop_translation_template(primary_template_path)
	if template is not None:
		return template

	primary_norm = os.path.normcase(os.path.normpath(primary_template_path))
	fallback_norm = os.path.normcase(os.path.normpath(fallback_template_path))
	if primary_norm == fallback_norm:
		return None

	return load_workshop_translation_template(fallback_template_path)

def render_workshop_translation_text(
	template,
	translated_title,
	translated_description,
	original_title,
	original_description,
	translated_language,
	original_language
):
	"""Render output using the template (or default format if missing)."""
	if not template:
		return build_workshop_translation_text(translated_title, translated_description)

	# Tokens are optional; missing values become empty strings.
	replacements = {
		"$Translated-Title$": translated_title or "",
		"$Original-Title$": original_title or "",
		"$Translated-Language$": translated_language or "",
		"$Original-Language$": original_language or "",
		"$Translated-Description$": translated_description or "",
		"$Original-Description$": original_description or ""
	}
	output = template
	for token, value in replacements.items():
		output = output.replace(token, value)
	return output

def translate_workshop_title(translator, title, deepl_code, source_lang_deepl):
	"""Translate the workshop title using DeepL."""
	try:
		result = translator.translate_text(
			title,
			target_lang=deepl_code,
			source_lang=source_lang_deepl
		)
		return cleanup_text(result.text)
	except Exception as e:
		print(f"  [Error] Failed to translate workshop title to {deepl_code}: {e}")
		return None

def translate_workshop_title_gemini(text, target_language, system_prompt):
	"""Translate the workshop title using Gemini."""
	if text == "":
		return ""
	prompt = _build_gemini_system_prompt(system_prompt, target_language)
	payload = {
		"systemInstruction": {"parts": [{"text": prompt}]},
		"contents": [
			{"role": "user", "parts": [{"text": text}]}
		]
	}

	response = _gemini_generate_content(payload)
	if response is None:
		return None

	translated_text = _gemini_extract_text(response)
	if translated_text is None:
		print("  [Error] Gemini API returned no text.")
		return None

	return cleanup_text(translated_text)

def translate_workshop_description(translator, text, deepl_code, source_lang_deepl):
	"""Translate the full workshop description using DeepL."""
	if text == "":
		return ""
	try:
		result = translator.translate_text(
			text,
			target_lang=deepl_code,
			source_lang=source_lang_deepl
		)
		translated_text = result.text
		if text.endswith("\n") and not translated_text.endswith("\n"):
			translated_text += "\n"
		return translated_text
	except Exception as e:
		print(f"  [Error] Failed to translate workshop description to {deepl_code}: {e}")
		return None

def _build_gemini_system_prompt(template, target_language):
	"""Fill the {target_language} placeholder in the system prompt."""
	try:
		return template.format(target_language=target_language)
	except Exception:
		return template

def _gemini_generate_content(payload):
	"""Call the Gemini generateContent API with retries."""
	if not GEMINI_API_KEY:
		print("Error: GEMINI_API_KEY not found in .env file.")
		print("Please create a .env file with GEMINI_API_KEY=your_key_here")
		return None

	url = f"{GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent"
	query = urllib.parse.urlencode({"key": GEMINI_API_KEY})
	request_body = json.dumps(payload).encode("utf-8")

	max_attempts = 3
	base_delay = 2

	# Retry transient failures with exponential backoff.
	for attempt in range(1, max_attempts + 1):
		request = urllib.request.Request(
			f"{url}?{query}",
			data=request_body,
			headers={"Content-Type": "application/json"},
			method="POST"
		)

		try:
			with urllib.request.urlopen(request, timeout=60) as response:
				raw = response.read().decode("utf-8")
			return json.loads(raw)
		except urllib.error.HTTPError as e:
			body = e.read().decode("utf-8", errors="ignore")
			retryable = e.code in (429, 500, 502, 503, 504)
			if retryable and attempt < max_attempts:
				delay = base_delay * (2 ** (attempt - 1))
				print(f"  [Warning] Gemini API request failed ({e.code}) on attempt {attempt}/{max_attempts}. Retrying in {delay}s...")
				time.sleep(delay)
				continue
			print(f"  [Error] Gemini API request failed ({e.code}): {body}")
			return None
		except urllib.error.URLError as e:
			if attempt < max_attempts:
				delay = base_delay * (2 ** (attempt - 1))
				print(f"  [Warning] Gemini API request failed ({e.reason}) on attempt {attempt}/{max_attempts}. Retrying in {delay}s...")
				time.sleep(delay)
				continue
			print(f"  [Error] Gemini API request failed: {e}")
			return None
		except Exception as e:
			if attempt < max_attempts:
				delay = base_delay * (2 ** (attempt - 1))
				print(f"  [Warning] Gemini API request failed ({e}) on attempt {attempt}/{max_attempts}. Retrying in {delay}s...")
				time.sleep(delay)
				continue
			print(f"  [Error] Gemini API request failed: {e}")
			return None

def _gemini_extract_text(response):
	"""Extract concatenated text from a Gemini response payload."""
	candidates = response.get("candidates") if isinstance(response, dict) else None
	if not candidates:
		return None
	content = candidates[0].get("content", {})
	parts = content.get("parts", []) if isinstance(content, dict) else []
	text_chunks = []
	for part in parts:
		text = part.get("text")
		if text:
			text_chunks.append(text)
	return "".join(text_chunks) if text_chunks else None

def translate_workshop_description_gemini(text, target_language, system_prompt):
	"""Translate the full workshop description using Gemini."""
	if text == "":
		return ""
	prompt = _build_gemini_system_prompt(system_prompt, target_language)
	payload = {
		"systemInstruction": {"parts": [{"text": prompt}]},
		"contents": [
			{"role": "user", "parts": [{"text": text}]}
		]
	}

	response = _gemini_generate_content(payload)
	if response is None:
		return None

	translated_text = _gemini_extract_text(response)
	if translated_text is None:
		print("  [Error] Gemini API returned no text.")
		return None

	if text.endswith("\n") and not translated_text.endswith("\n"):
		translated_text += "\n"
	return translated_text

def translate_workshop_assets(
	translator,
	source_language,
	source_lang_deepl,
	cache_bucket,
	workshop_description_translator,
	gemini_description_system_prompt,
	workshop_title_translator,
	gemini_title_system_prompt,
	workshop_item_id,
	metadata_path,
	workshop_description_path,
	workshop_translations_dir,
	workshop_template_path,
	main_workshop_template_path,
	log_prefix
):
	"""Translate workshop titles/descriptions and update cache metadata."""
	has_description_file = os.path.exists(workshop_description_path)
	if not has_description_file:
		print(f"{log_prefix}Workshop description not found: {workshop_description_path}; skipping workshop translations.")
		return False

	title = load_workshop_title(metadata_path)
	raw_description = load_workshop_description(workshop_description_path)
	translatable_description, _ = split_workshop_description(raw_description)
	description = apply_workshop_item_id(translatable_description, workshop_item_id)
	if description is None:
		print(f"{log_prefix}Workshop description could not be read; skipping workshop translations.")
		return False

	translation_template = resolve_workshop_translation_template(
		workshop_template_path,
		main_workshop_template_path
	)

	os.makedirs(workshop_translations_dir, exist_ok=True)

	workshop_cache = cache_bucket.setdefault("workshop", {})
	# Cache raw translated title/description per language so template changes don't force retranslation.
	translation_cache = workshop_cache.setdefault("translations", {})
	description_changed = False
	translator_changed = workshop_cache.get("description_translator") != workshop_description_translator
	description_hash = None
	if description is not None:
		description_hash = hash_text(description)
		# Re-translate when source text or provider changes.
		description_changed = workshop_cache.get("description_hash") != description_hash or translator_changed

	title_translator_changed = workshop_cache.get("title_translator") != workshop_title_translator
	template_hash = hash_text(translation_template) if translation_template is not None else None
	template_changed = template_hash != workshop_cache.get("template_hash")

	description_success = True
	title_success = True
	cache_changed = False

	for folder_name, deepl_code in TARGET_LANGUAGES.items():
		if folder_name == source_language:
			continue

		translation_path = os.path.join(
			workshop_translations_dir,
			WORKSHOP_TRANSLATION_FILENAME.format(lang=folder_name)
		)
		file_changed = False
		cache_entry = translation_cache.setdefault(folder_name, {})
		cached_title = cache_entry.get("title")
		cached_description = cache_entry.get("description")

		if title:
			if cached_title is None or title_translator_changed:
				provider_label = "gemini-3-flash" if workshop_title_translator == "gemini-3-flash" else "deepl"
				print(f"{log_prefix}Translating workshop title -> {folder_name} ({provider_label})...")
				if workshop_title_translator == "gemini-3-flash":
					target_language = LANGUAGE_DISPLAY_NAMES.get(folder_name, folder_name)
					translated_title = translate_workshop_title_gemini(
						title,
						target_language,
						gemini_title_system_prompt
					)
				else:
					translated_title = translate_workshop_title(
						translator,
						title,
						deepl_code,
						source_lang_deepl
					)
				if translated_title is not None:
					cached_title = translated_title
					cache_entry["title"] = translated_title
					cache_changed = True
					file_changed = True
				else:
					title_success = False
			else:
				print(f"{log_prefix}Workshop title cached -> {folder_name}; skipping.")

		if description is not None:
			needs_description = description_changed or cached_description is None
			if needs_description:
				provider_label = "gemini-3-flash" if workshop_description_translator == "gemini-3-flash" else "deepl"
				print(f"{log_prefix}Translating workshop description -> {folder_name} ({provider_label})...")
				if workshop_description_translator == "gemini-3-flash":
					target_language = LANGUAGE_DISPLAY_NAMES.get(folder_name, folder_name)
					translated_description = translate_workshop_description_gemini(
						description,
						target_language,
						gemini_description_system_prompt
					)
				else:
					translated_description = translate_workshop_description(
						translator,
						description,
						deepl_code,
						source_lang_deepl
					)
				if translated_description is None:
					description_success = False
					continue
				cached_description = translated_description
				cache_entry["description"] = translated_description
				cache_changed = True
				file_changed = True
			else:
				print(f"{log_prefix}Workshop description unchanged -> {folder_name}; skipping.")

		if file_changed or template_changed or not os.path.exists(translation_path):
			if cached_title is None and cached_description is None:
				continue
			translated_language = LANGUAGE_DISPLAY_NAMES.get(folder_name, folder_name)
			original_language = LANGUAGE_DISPLAY_NAMES.get(source_language, source_language)
			output = render_workshop_translation_text(
				translation_template,
				cached_title,
				cached_description,
				title,
				description,
				translated_language,
				original_language
			)
			with open(translation_path, "w", encoding="utf-8") as f:
				f.write(output)

	if description is not None and description_changed and description_success:
		workshop_cache["description_hash"] = description_hash
		workshop_cache["description_translator"] = workshop_description_translator
		cache_changed = True

	if title_success and workshop_cache.get("title_translator") != workshop_title_translator:
		workshop_cache["title_translator"] = workshop_title_translator
		cache_changed = True

	if workshop_cache.get("template_hash") != template_hash:
		workshop_cache["template_hash"] = template_hash
		cache_changed = True

	return cache_changed

def main():
	"""Script entry point."""
	args = parse_args()

	translator = get_translator()
	if not translator:
		return

	(
		source_language,
		translate_workshop,
		translate_submods_by_default,
		localization_translator,
		gemini_localization_system_prompt,
		workshop_description_translator,
		gemini_description_system_prompt,
		workshop_title_translator,
		gemini_title_system_prompt,
		workshop_item_id
	) = load_config(CONFIG_PATH)
	if not source_language:
		return

	source_lang_id = LANGUAGE_CONFIG[source_language]["loc_id"]
	source_lang_deepl = LANGUAGE_CONFIG[source_language]["deepl"]

	# Load existing hash cache to identify changed keys.
	hash_data = load_hashes(HASHES_PATH)
	hashes_modified = False

	include_submods = args.submods or translate_submods_by_default
	targets = build_translation_targets(include_submods)
	if include_submods:
		active_submods = {target["cache_key"] for target in targets if target["cache_key"] != "main"}
		submods_cache = hash_data.get("submods")
		if isinstance(submods_cache, dict):
			for cache_key in list(submods_cache.keys()):
				if cache_key not in active_submods:
					del submods_cache[cache_key]
					hashes_modified = True

	for target in targets:
		cache_key = target["cache_key"]
		log_prefix = target["log_prefix"]
		loc_base_path = target["loc_base_path"]
		source_dir = os.path.join(loc_base_path, source_language)
		cache_bucket = get_cache_bucket(hash_data, cache_key)
		file_hashes = cache_bucket["files"]
		processed_files = set()

		if os.path.exists(source_dir):
			for root, _, files in os.walk(source_dir):
				for file in files:
					if not file.endswith(".yml"):
						continue

					source_filepath = os.path.join(root, file)
					with open(source_filepath, 'r', encoding='utf-8-sig') as f:
						source_lines = f.readlines()

					# Build per-key hashes from the source file.
					source_entries = parse_source_entries(source_lines)
					source_hashes = {}
					for entry in source_entries:
						source_hashes[entry["key"]] = hash_text(entry["value"])

					source_rel_path = os.path.relpath(source_filepath, loc_base_path)
					processed_files.add(source_rel_path)

					# Determine which keys changed since last run.
					prev_hashes = file_hashes.get(source_rel_path, {})
					changed_keys = set()
					for key, current_hash in source_hashes.items():
						if prev_hashes.get(key) != current_hash:
							changed_keys.add(key)

					for folder_name, deepl_code in TARGET_LANGUAGES.items():
						if folder_name == source_language:
							continue
						process_file(
							translator,
							source_lines,
							source_entries,
							source_filepath,
							loc_base_path,
							folder_name,
							deepl_code,
							source_lang_id,
							source_lang_deepl,
							changed_keys,
							localization_translator,
							gemini_localization_system_prompt,
							log_prefix
						)

					# Persist updated hashes for this file.
					if prev_hashes != source_hashes:
						file_hashes[source_rel_path] = source_hashes
						hashes_modified = True

			# Drop cache entries for source files that no longer exist.
			for rel_path in list(file_hashes.keys()):
				if rel_path not in processed_files:
					del file_hashes[rel_path]
					hashes_modified = True
		else:
			print(f"{log_prefix}Localization source directory not found: {source_dir}; skipping localization translation.")
			if file_hashes:
				file_hashes.clear()
				hashes_modified = True

		# Optionally translate workshop title/description.
		if translate_workshop:
			hashes_modified = translate_workshop_assets(
				translator,
				source_language,
				source_lang_deepl,
				cache_bucket,
				workshop_description_translator,
				gemini_description_system_prompt,
				workshop_title_translator,
				gemini_title_system_prompt,
				workshop_item_id,
				target["metadata_path"],
				target["workshop_description_path"],
				target["workshop_translations_dir"],
				target["workshop_template_path"],
				WORKSHOP_TRANSLATION_TEMPLATE_PATH,
				log_prefix
			) or hashes_modified

	# Write cache only if something changed.
	if hashes_modified:
		save_hashes(HASHES_PATH, hash_data)

	print("Translation complete!")

if __name__ == "__main__":
	main()
