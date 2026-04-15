# Verify Skill

Verify that a code change does what it should by running the application.

## Purpose

After implementing a change, use this skill to:
1. **Verify functionality** — Does the change work as intended?
2. **Run tests** — Do existing tests pass?
3. **Check edge cases** — Are there any regressions?
4. **Validate behavior** — Does the code behave correctly in various scenarios?

## When to Use

Use when:
- User wants to verify a change works correctly
- After making a fix or implementing a feature
- Before committing or creating a PR
- When troubleshooting a reported issue

## Verification Steps

### 1. Understand the Change

Review what was changed:
- Run `git diff` or `git diff HEAD` to see changes
- Read modified files to understand the implementation
- Identify the expected behavior

### 2. Run Basic Tests

```bash
# Find and run project tests
npm test        # Node projects
pytest          # Python projects
go test ./...   # Go projects
cargo test      # Rust projects
```

### 3. Test the Specific Change

For the specific functionality changed:
- Create test cases for the new behavior
- Run manual tests if automated tests aren't available
- Verify edge cases are handled

### 4. Check for Regressions

- Run the full test suite if available
- Test related functionality
- Verify no breaking changes

## Verification Checklist

- [ ] Code compiles/builds without errors
- [ ] New tests pass
- [ ] Existing tests still pass
- [ ] Manual testing confirms expected behavior
- [ ] Edge cases are handled
- [ ] No regressions in related functionality

## Reporting

Present verification results clearly:

```
Verification Results
====================

Change: [brief description]
Status: [PASS/FAIL]

Tests Run:
- unit tests: ✓
- integration tests: ✓

Issues Found:
- None

Recommendations:
- Ready to merge
```

## Tips

- Start with the simplest verification first
- If tests fail, fix the tests or the code
- Document any known limitations
- Don't skip edge case testing
