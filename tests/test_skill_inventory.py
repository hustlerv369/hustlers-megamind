import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import skills

def test_retired_bulk_disable_cannot_move_sources(tmp_path, monkeypatch):
    active = tmp_path / "skills"
    note = active / "important" / "SKILL.md"
    note.parent.mkdir(parents=True)
    note.write_text("critical capability", encoding="utf-8")
    monkeypatch.setattr(skills, "SKILLS_DIR", active)
    monkeypatch.setattr(skills, "DISABLED_DIR", tmp_path / "disabled")
    assert skills.main(["skills.py", "disable", "--unused", "0"]) == 2
    assert note.read_text(encoding="utf-8") == "critical capability"
    assert not (tmp_path / "disabled").exists()

def test_inventory_has_no_result_count_cap(tmp_path):
    for i in range(35):
        p = tmp_path / f"skill-{i}" / "SKILL.md"
        p.parent.mkdir()
        p.write_text("reference", encoding="utf-8")
    assert len(skills.inventory(tmp_path)) == 35
