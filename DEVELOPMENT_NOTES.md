# Development Notes

## AI Assistant Optimization Preferences

### File Reading Optimization
To reduce token usage while maintaining quality, skip unnecessary file reads when:

- **Git operations**: Use `git status`, `git diff --stat` instead of reading files
- **Code search**: Use `grep` or `codebase_search` to find specific patterns
- **Understanding changes**: Use `git diff` or file metadata instead of full reads
- **Debugging**: Read only relevant sections, not entire files
- **Context available**: Rely on conversation history/summaries when sufficient

Read files when:
- User explicitly asks to review/read something
- Need to understand complex logic to make changes
- Error debugging requires full context
- Making code changes that need exact structure
- Quality would suffer without reading (refactoring, complex logic changes)

### General Principles
- Minimize token usage without sacrificing output quality
- Use tool outputs (git, grep, etc.) instead of reading files when possible
- Read files only when necessary for the task at hand

