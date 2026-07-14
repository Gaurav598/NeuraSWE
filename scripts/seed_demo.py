"""Seed the database with a sample completed run so the dashboard has content
for demos. Usage (from server/): python ../scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from app.db import crud  # noqa: E402
from app.db.base import SessionLocal, init_models  # noqa: E402
from app.db.models import RunStatus  # noqa: E402

DEMO_STEPS = [
    ("The issue is about email validation failing for '+' characters. I'll search "
     "for the login handler and email parsing logic.",
     "search_code", {"query": "email validation login"},
     "Found 3 chunks:\n1. src/auth/login.ts:23-45 — validateEmail\n"
     "2. src/utils/validators.ts:12-18 — isValidEmail"),
    ("validateEmail looks most relevant. Let me read it.",
     "read_file", {"path": "src/auth/login.ts", "start_line": 23, "end_line": 45},
     "function validateEmail(email) {\n  const re = /^[a-zA-Z0-9._-]+@.../;\n  return re.test(email);\n}"),
    ("Line 34 regex disallows '+' in the local part, which RFC 5322 permits. I'll fix the regex.",
     "edit_file", {"path": "src/auth/login.ts", "old_text": "[a-zA-Z0-9._-]+@",
                   "new_text": "[a-zA-Z0-9._%+-]+@"},
     "Successfully edited src/auth/login.ts. Replaced a 1-line block."),
    ("Add a regression test for '+' emails.",
     "create_file", {"path": "src/auth/__tests__/login.plus.test.ts",
                     "content": "test('+ email', () => { ... })"},
     "Created src/auth/__tests__/login.plus.test.ts (8 lines)."),
    ("Run the test suite to confirm nothing breaks.",
     "run_tests", {},
     "Summary: {\"passed\": 49, \"failed\": 0, \"success\": true}"),
    ("All green. Submitting.",
     "submit_solution", {},
     "Solution submitted. Tests pass. A pull request will be created."),
]


async def main() -> None:
    await init_models()
    async with SessionLocal() as session:
        repo = await crud.upsert_repository(session, owner="acme", name="webapp")
        run = await crud.create_run(
            session,
            repository_id=repo.id,
            issue_number=42,
            issue_title="Login fails when email has + character",
            issue_body="Users with addresses like a+b@x.com cannot log in.",
            model="deepseek-coder-v2:16b",
        )
        for i, (thought, tool, args, obs) in enumerate(DEMO_STEPS, 1):
            await crud.add_step(
                session, run_id=run.id, step_number=i, thought=thought,
                tool_name=tool, tool_args=args, observation=obs,
                duration_ms=1800 + i * 300, token_count=900 + i * 50,
            )
        await crud.update_run(
            session, run,
            status=RunStatus.SOLVED, total_steps=len(DEMO_STEPS), duration_ms=34200,
            pr_number=128, pr_url="https://github.com/acme/webapp/pull/128",
            baseline_tests={"passed": 47, "failed": 1, "success": False},
            final_tests={"passed": 49, "failed": 0, "success": True},
        )
        await session.commit()
        print(f"Seeded demo run {run.id} for {repo.full_name}")


if __name__ == "__main__":
    asyncio.run(main())
