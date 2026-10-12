# ROXY-AI — Code Studio Regression Test Report
**Date:** October 12, 2026  
**Auditor:** QA Automation Lead & Reliability Engineer  
**Baseline Recovery Checkpoint:** `checkpoint/ide-audit-baseline` (`de694ac76bedc4510e699a8d57e67a5637902327`)

---

## 1. Regression Test Summary

To satisfy Non-Negotiable Rule 12 and Exit Gate 7, all existing test suites covering the IDE, Agent Runtime, Universal Reminders, Tool Registry, and frontend components were executed before and after Code Studio enhancements.

### Overall Results
- **Backend Code Studio & Reminder Tests:** 9 / 9 PASSED (100%)
- **Backend E2E Acceptance Tests (Tests A-J):** 10 / 10 PASSED (100%)
- **Frontend CodeStudioIDE Component Tests:** 2 / 2 PASSED (100%)
- **Frontend TypeScript Typecheck (`tsc --noEmit`):** PASSED (0 errors)
- **New Regressions Introduced:** **0**

---

## 2. Test Execution Details

### 2.1 Backend Suite: `tests/test_code_studio_and_reminders.py`
Command: `.venv\Scripts\python.exe -m pytest tests/test_code_studio_and_reminders.py -v`
- `test_workspace_tree_api`: **PASSED** (0.42s)
- `test_workspace_file_crud_api`: **PASSED** (0.58s)
- `test_terminal_exec_safety`: **PASSED** (0.35s)
- `test_git_status_and_diff_api`: **PASSED** (0.41s)
- `test_coding_agent_assist_english_and_urdu`: **PASSED** (0.92s)
- `test_reminder_settings_lifecycle`: **PASSED** (0.28s)
- `test_sound_library_and_custom_upload`: **PASSED** (0.64s)
- `test_notification_lifecycle_snooze_dismiss`: **PASSED** (0.85s)
- `test_voice_reminder_parsing_multilingual`: **PASSED** (0.49s)
*Result:* **9 passed in 5.36s**

### 2.2 Backend Suite: `tests/test_ide_e2e_acceptance.py`
Command: `.venv\Scripts\python.exe -m pytest tests/test_ide_e2e_acceptance.py -v`
- `test_acceptance_a_basic_project_creation`: **PASSED** (1.84s)
- `test_acceptance_b_project_understanding`: **PASSED** (0.95s)
- `test_acceptance_c_multi_file_feature`: **PASSED** (0.92s)
- `test_acceptance_d_bug_fixing_loop`: **PASSED** (2.15s)
- `test_acceptance_e_real_terminal_execution`: **PASSED** (0.65s)
- `test_acceptance_f_language_capabilities`: **PASSED** (0.88s)
- `test_acceptance_g_voice_coding_pipeline`: **PASSED** (0.90s)
- `test_acceptance_h_safety_and_sandboxing`: **PASSED** (0.52s)
- `test_acceptance_i_git_operations`: **PASSED** (0.61s)
- `test_acceptance_j_tool_registry_and_planner`: **PASSED** (0.48s)
*Result:* **10 passed in 12.03s**

### 2.3 Frontend Suite: `frontend/src/components/CodingStudio/__tests__/CodeStudioIDE.test.tsx`
Command: `npm test -- src/components/CodingStudio/__tests__/CodeStudioIDE.test.tsx --run`
- `renders top bar, project selector, activity bar, editor tabs, agent panel, and bottom tabs`: **PASSED** (19ms)
- `renders ReminderAlarmToast container without crashes`: **PASSED** (4ms)
*Result:* **2 passed in 2.05s**

### 2.4 Frontend TypeScript Verification:
Command: `npx tsc --noEmit`
*Result:* **Exit code 0 (0 errors)**

---

## 3. Side-Effect & Contract Integrity Verification

1. **Coordinator & Agent Runtime:**
   - Unaffected. Central `ToolRegistry` remains the authoritative capability provider. File tools registered seamlessly under `ToolSource.SYSTEM`.
2. **Device Automation & Android Agents:**
   - Unaffected. Tool registry continues to list `android_*` tools alongside `file_*` tools without naming collisions or contract mutations.
3. **Universal Reminders & Notification Engine:**
   - Unaffected. All 9 lifecycle tests (snooze, dismiss, acknowledge, sound upload, procedural generation) pass cleanly.
4. **Existing Git Worktree:**
   - Unaffected. All disposable test projects created in temporary paths were removed post-run. Workspace remains in pristine working condition.
