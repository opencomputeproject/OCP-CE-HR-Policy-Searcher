# Continuity Document: File-Based Domain Targeting

## What was done
Added the ability to use `--domains <filename>` to target all enabled domains from a specific YAML file in `config/domains/`, without requiring an entry in `groups.yaml`.

## Files modified
1. **`src/config/loader.py`**
   - `_load_domains_directory()`: Tags each domain dict with `_source_file = yaml_file.stem`
   - `get_enabled_domains()`: Added file-name fallback between group lookup and error. Resolution order: "all" -> groups.yaml -> file name -> error
   - Added `get_available_domain_files()` helper returning `{file_stem: enabled_count}`
   - Enhanced error message to show available groups AND domain files

2. **`src/main.py`**
   - Added `get_available_domain_files` to imports
   - Updated `--domains` help text (main parser + estimate-cost) to mention "file name"
   - Updated `cmd_list_groups()` to display domain files not already covered by groups

3. **`tests/unit/test_config_loader.py`**
   - Added `test_domains_tagged_with_source_file` in TestLoadDomainsDirectory
   - Added 4 tests in TestGetEnabledDomains: file_name_fallback, group_takes_priority_over_file, file_fallback_skips_disabled, error_shows_available_files
   - Added new TestGetAvailableDomainFiles class with 4 tests
   - Added 2 integration tests in TestLoadSettingsIntegration: file_targeting_germany, domains_have_source_file_tags

4. **`README.md`**
   - Updated `--domains` description
   - Added "Domain Files" subsection with examples
   - Added file-based example to Examples section

## Design decisions
- Groups take priority over file names when names conflict (backward compatible)
- `_source_file` follows existing pattern from rejected sites loader (line 82)
- Error message shows only file names not already covered by group names to reduce confusion
- `_source_file` is internal metadata (underscore prefix convention), not exposed by `list_domains()`

## Testing status
- [ ] Unit tests (test_config_loader.py)
- [ ] Full regression (all test files)
- [ ] Ruff linter
- [ ] Commit created
