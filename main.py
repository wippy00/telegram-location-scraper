import runpy
import traceback
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent

IMPORT_SCRIPT = ROOT_DIR / "importers" / "telegram.py"
CATEGORIZER_SCRIPT = ROOT_DIR / "workers" / "categorizer.py"
ADDRESS_SCRIPT = ROOT_DIR / "workers" / "address.py"
INSTAGRAM_SCRIPT = ROOT_DIR / "workers" / "instagram.py"
OCR_SCRIPT = ROOT_DIR / "workers" / "ocr.py"
AI_SCRIPT = ROOT_DIR / "workers" / "ai_extractor.py"
MAPS_SCRIPT = ROOT_DIR / "workers" / "maps.py"
RESPONSE_SCRIPT = ROOT_DIR / "workers" / "response.py"


def _run_step(step_name: str, script_path: Path) -> bool:
	print(f"\n[Orchestrator] STEP '{step_name}'")
	try:
		runpy.run_path(str(script_path), run_name="__main__")
	except SystemExit as e:
		if e.code not in (0, None):
			print(f"[Orchestrator] STEP '{step_name}' failed (exit={e.code})")
			return False
	except Exception:
		print(f"[Orchestrator] STEP '{step_name}' failed")
		traceback.print_exc()
		return False

	print(f"[Orchestrator] STEP '{step_name}' completed")
	return True


def run_import() -> bool:
	return _run_step("import", IMPORT_SCRIPT)


def categorizer() -> bool:
	return _run_step("categorizer", CATEGORIZER_SCRIPT)


def address() -> bool:
	return _run_step("address", ADDRESS_SCRIPT)


def instagram() -> bool:
	return _run_step("instagram", INSTAGRAM_SCRIPT)


def ocr() -> bool:
	return _run_step("ocr", OCR_SCRIPT)


def ai() -> bool:
	return _run_step("ai", AI_SCRIPT)


def maps() -> bool:
	return _run_step("maps", MAPS_SCRIPT)


def response() -> bool:
	return _run_step("response", RESPONSE_SCRIPT)


def main() -> int:
	print("[Orchestrator] Pipeline avviata.")

	step_results = [
		run_import(),
    
		categorizer(),
	
    	instagram(),
		ocr(),
		ai(),
		maps(),
		

		address(),
		
        
        # response(),
	]
	has_failures = not all(step_results)

	if has_failures:
		print("\n[Orchestrator] Pipeline terminata con errori.")
		return 1

	print("\n[Orchestrator] Pipeline completata con successo.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())