# Conditional Logic Integration Test Plan

## Status: ⏳ Awaiting Test App

The example test files in this directory demonstrate conditional logic operators but use a placeholder app (`com.example.testapp`). To complete integration testing, these tests need to be adapted for a real test application.

## Test Files

This directory contains three example test files demonstrating conditional logic:

- [conditional-basic.test.yaml](./conditional-basic.test.yaml) - All 5 operators
- [conditional-nested.test.yaml](./conditional-nested.test.yaml) - 2-3 level nesting
- [conditional-screen.test.yaml](./conditional-screen.test.yaml) - AI vision checks

These files serve as documentation and will be templates for real app testing.

## Test Prerequisites

- [ ] Device connected and accessible via mobile-mcp
- [ ] Test application installed (real app, not placeholder)
- [ ] Example test files adapted to use real app package and elements

## Test Cases

### 1. Basic Conditionals (conditional-basic.test.yaml)

**Operators to verify:**
- `if_exists` - Single element check with then/else branches
- `if_not_exists` - Inverse check
- `if_all_exist` - Multiple elements AND logic
- `if_any_exist` - Multiple elements OR logic
- Condition without else branch

**Expected behavior:**
*Note: Conditionals check current state once without retries or polling, unlike `wait_for` which polls until timeout. Use `wait_for` before conditionals if elements might be loading.*

- Conditionals evaluate instantly (no retries)
- Element checks complete in <50ms typically
- Branch steps show decimal notation (3.1/8, 3.2/8)
- Correct branch executes based on condition result
- Missing else branch skips gracefully

### 2. Nested Conditionals (conditional-nested.test.yaml)

**Nesting levels to verify:**
- 2-level nesting
- 3-level nesting
- Mixed operators (if_all_exist → if_any_exist → if_exists)

**Expected behavior:**
- Inner conditionals execute correctly
- Step numbering tracks through nesting (3.1.1/8)
- Outer conditional continues after inner completes
- No interference between nesting levels

### 3. Screen-Based Conditionals (conditional-screen.test.yaml)

**Operators to verify:**
- `if_screen` with AI vision analysis
- Nested combinations of if_screen and if_exists
- Combined element + vision checks

**Expected behavior:**
- Screenshots captured correctly
- AI vision analysis returns appropriate result
- Performance ~1-2s per if_screen check
- Combined checks work correctly

### 4. Error Handling

**Scenarios to test:**

**4.1 Missing then key:**
```yaml
- if_exists: "Button"
  # Missing then key
  else:
    - tap: "Other"
```
**Expected:** Test fails immediately with error: `✗ FAILED: Conditional missing required 'then' key at step {N}`

**4.2 Empty branches:**
```yaml
- if_exists: "Dialog"
  then: []
```
**Expected:** Valid no-op, continues to next step

**4.3 API failures:**
- Element list retrieval fails
- if_screen screenshot/analysis fails

**Expected:** Warning logged, condition treated as false, test continues

## Verification Checklist

When integration testing is performed, verify:

- [ ] All 5 operators work correctly (if_exists, if_not_exists, if_all_exist, if_any_exist, if_screen)
- [ ] Nested conditionals execute properly (tested 2-3 levels)
- [ ] Instant evaluation confirmed (no retry behavior)
- [ ] Error handling graceful (test doesn't crash)
- [ ] Output formatting clear and consistent
- [ ] Step numbering correct (decimal notation for branches)
- [ ] Branch selection correct (then vs else)
- [ ] Empty branches handled as no-op
- [ ] API failures treated as false condition

## Test Results Template

When tests are run, document results here:

```markdown
## Test Execution Results

**Date:** [YYYY-MM-DD]
**Device:** [Device Name/ID]
**App:** [Real app package name]
**Tester:** [Name]

### conditional-basic.test.yaml

- [ ] ✅/❌ if_exists: [Result and notes]
- [ ] ✅/❌ if_not_exists: [Result and notes]
- [ ] ✅/❌ if_all_exist: [Result and notes]
- [ ] ✅/❌ if_any_exist: [Result and notes]
- [ ] ✅/❌ Condition without else: [Result and notes]

### conditional-nested.test.yaml

- [ ] ✅/❌ Two-level nesting: [Result and notes]
- [ ] ✅/❌ Three-level nesting: [Result and notes]
- [ ] ✅/❌ Mixed operators: [Result and notes]

### conditional-screen.test.yaml

- [ ] ✅/❌ if_screen: [Result and notes]
- [ ] ✅/❌ Nested with elements: [Result and notes]
- [ ] ✅/❌ Combined checks: [Result and notes]

### Error Handling

- [ ] ✅/❌ Missing then key: [Result and notes]
- [ ] ✅/❌ Empty branches: [Result and notes]
- [ ] ✅/❌ API failures: [Result and notes]

### Issues Found

[List any issues, unexpected behavior, or bugs discovered]

### Performance Notes

- if_screen average time: [X seconds]
- Element checks average time: [X milliseconds]
- Nested conditional overhead: [Notes]

### Conclusion

[Overall assessment: Ready for production / Needs fixes / etc.]
```

## Next Steps

1. Identify or create a real test application with:
   - Various UI states (dialogs, loading states, premium/free modes)
   - Multiple screen variations for testing conditionals
   - Elements that can be reliably targeted

2. Adapt example test files to use real app:
   - Change `com.example.testapp` to actual package name
   - Update element names to match real app elements
   - Adjust screen descriptions for if_screen checks

3. Run adapted tests on real device

4. Document results using template above

5. Fix any issues discovered and re-test
