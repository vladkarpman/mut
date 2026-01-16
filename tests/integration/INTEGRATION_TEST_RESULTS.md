# Integration Test Results

> **Status:** Template created - awaiting manual test execution
>
> To execute tests:
> 1. Ensure Android device is connected via adb
> 2. cd tests/integration
> 3. ./run-integration-tests.sh
> 4. Follow prompts and fill in results below

**Date:** [Fill in execution date]
**Device:** [Fill in device name/model]
**Android Version:** [Fill in Android version]
**Calculator Package:** [Fill in from test output]
**Tester:** [Your name]

## Environment

- adb version: [Fill in]
- ffmpeg version: [Fill in if available]
- Device resolution: [Fill in]

## Command Testing Results

### /create-test
- [x] Creates file successfully: YES/NO
- [x] Template structure correct: YES/NO
- Issues: [Any issues encountered]

### /generate-test
- [x] Generates valid YAML: YES/NO
- [x] Actions mapped correctly: YES/NO
- Issues: [Any issues encountered]

### /run-test
- [x] Executes basic-operations.test.yaml: YES/NO
- [x] Shows step-by-step output: YES/NO
- [x] All steps pass: YES/NO
- Issues: [Any issues encountered]

### /record-test + /stop-recording
- [x] Records touch events: YES/NO
- [x] Extracts frames correctly: YES/NO
- [x] Identifies elements via vision: YES/NO
- [x] Generates test.yaml: YES/NO
- Issues: [Any issues encountered]

## Conditional Operators Results

### if_exists
- [x] Simple check works: YES/NO
- [x] Then branch executes: YES/NO
- [x] Else branch executes when false: YES/NO
- Issues: [Any issues encountered]

### if_not_exists
- [x] Inverse logic correct: YES/NO
- Issues: [Any issues encountered]

### if_all_exist
- [x] AND logic correct: YES/NO
- [x] All elements verified: YES/NO
- Issues: [Any issues encountered]

### if_any_exist
- [x] OR logic correct: YES/NO
- [x] First match used: YES/NO
- Issues: [Any issues encountered]

### if_screen
- [x] AI vision analysis works: YES/NO
- [x] Performance acceptable: YES/NO
- [x] Accuracy good: YES/NO
- Execution time: [X seconds]
- Issues: [Any issues encountered]

### Nested Conditionals
- [x] 2-level nesting works: YES/NO
- [x] Step numbering correct (3.1, 3.2): YES/NO
- [x] Branches execute correctly: YES/NO
- Issues: [Any issues encountered]

## Performance Metrics

- Basic test execution time: [X seconds]
- Conditional test execution time: [X seconds]
- Average element finding time: [X ms]
- Average if_screen time: [X seconds]

## Issues Discovered

[List all issues, bugs, unexpected behaviors found during testing]

1. Issue: [Description]
   - Severity: Critical/High/Medium/Low
   - Steps to reproduce:
   - Expected behavior:
   - Actual behavior:

## Edge Cases Found

[List any edge cases or special scenarios discovered]

## Recommendations

[List recommended fixes, improvements, or documentation updates]

## Overall Assessment

- Commands working: X/5
- Conditional operators working: X/5
- Ready for documentation update: YES/NO
- Recommended version bump: Patch/Minor/Major
- Notes: [Overall assessment]
