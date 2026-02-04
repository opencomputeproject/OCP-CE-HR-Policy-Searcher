# Implementation Request

## Task
[Describe what you want implemented]

## Environment
- Python
- Open-source project (OCP Heat Reuse Policy Tracker)
- Semantic versioning in use

---

## Execution Protocol

### 1. Pre-Implementation
- Analyze full scope of changes needed
- Identify all files, functions, and components affected
- Consider edge cases and potential breaking changes
- Create/update TODO.md checklist for tracking progress
- Create/update CONTINUITY.md with current state and context for session recovery

### 2. Implementation
- Keep changes minimal and focused
- Prioritize user simplicity
- Follow existing code patterns and conventions
- Maintain type hints consistent with existing code
- Document non-obvious decisions inline

### 3. Dependencies
- Update requirements.txt or pyproject.toml if adding dependencies
- Note any new dependencies in CHANGELOG.md

### 4. Testing
- Create/update unit tests for new functionality
- Run full regression test suite
- Run linter if project has one configured
- Fix any failures before proceeding

### 5. Documentation
- Update README.md with any user-facing changes
- Update CHANGELOG.md under [Unreleased] section
- Update CONTINUITY.md with final state
- Bump version in pyproject.toml if appropriate (patch/minor)

### 6. Commit
- Run all tests one final time
- Create detailed commit message using this format:
```
  <type>(<scope>): <short description>

  <body - what changed and why>

  <footer - breaking changes, issues closed, etc.>
```
  Types: feat, fix, docs, refactor, test, chore
- Create the full commit message
- Commit automatically
- Push automatically
# - **STOP and show me the commit message**
# - **Wait for my approval before committing**
# - **After commit, ask before pushing to remote**

---

## Constraints
# - Do not commit or push without explicit approval
- If tests fail, fix before proceeding
- If scope exceeds estimate or architectural decisions arise, pause and discuss
- If stuck >10 minutes on one issue, report status
- If changes exceed ~500 lines, check in before continuing

## Progress Tracking
- Pause and summarize after completing each major TODO item
- Keep CONTINUITY.md current in case of context window compaction