# Task Management Guidelines

**Core Rule: Every task gets its own directory under `docs/tasks/`**

This document defines how to manage tasks in the Voice Mode project.

## Directory Structure

```
docs/
├── tasks/                    # Active development work
│   ├── README.md            # Task list and status
│   ├── archive/             # Completed task documentation
│   ├── implementation-notes.md  # Ongoing implementation decisions
│   ├── key-insights.md      # Important learnings
│   └── [task-name]/         # Task-specific directory
│       ├── README.md        # Task overview and links to all files
│       ├── design.md        # Design and specification (if needed)
│       └── implementation.md # Implementation notes (if needed)
├── specs/                   # Technical specifications
└── [general docs]           # User guides, configuration, etc.
```

## Task Lifecycle

### 1. Creating a New Task
**All tasks must have their own directory under `docs/tasks/`**

Steps:
1. Create directory: `docs/tasks/[task-name]/`
2. Create `docs/tasks/[task-name]/README.md` with:
   - Task description and goals
   - Current status
   - Links to all files in the directory
3. Add entry to `docs/tasks/README.md` with link to task directory
4. For complex tasks, add:
   - `design.md` - Initial specification
   - `implementation.md` - Implementation decisions

### 2. Working on Tasks
- Keep all task-related files in the task's directory
- Update the task's README.md with progress and new files
- Update main tasks/README.md status as work progresses
- Document key decisions in the global implementation-notes.md
- Add important learnings to the global key-insights.md

### 3. Completing Tasks
- Move task from active section to "Recently Completed" in README.md
- Include links to relevant documentation
- Extract key insights before archiving

### 4. Archiving Tasks
Archive a task when:
- Implementation is fully complete
- No outstanding issues remain
- All useful information has been extracted

Archive process:
1. Move entire task directory to `archive/` directory
2. Update links in tasks/README.md to point to archived location
3. If design docs are still relevant for future work, consider:
   - Copying them to specs/ directory
   - Creating a summary in specs/ with link to archived task

## Document Types

### Task Documentation
- **Design documents**: Initial planning and specifications
- **Implementation notes**: Decisions made during development
- **Key insights**: Important learnings to preserve

### Specifications (docs/specs/)
- Technical specifications that outlast individual tasks
- Architectural decisions and patterns
- Integration guides and protocols

## Best Practices

### Keep Related Things Together
- During active development, keep specs with their tasks
- Use descriptive filenames that group related documents
- Consider symlinks if documents need to exist in multiple places

### When to Move to specs/
Move documentation to specs/ when:
- It describes a stable, implemented feature
- It provides ongoing architectural guidance
- Multiple future tasks will reference it

### Task README Organization
- **The One Thing**: Single most important current task
- **High Priority**: Critical tasks that block progress
- **Medium Priority**: Important but not blocking
- **Low Priority**: Nice-to-have improvements
- **Ideas to Explore**: Future possibilities
- **Inbox**: New ideas to be triaged
- **Recently Completed**: Finished work with links

### Documentation Updates
- Update CHANGELOG.md when completing user-facing features
- Review and update README.md when archiving tasks
- Keep implementation-notes.md current with decisions

## Examples

### Example Task Structure
```
docs/tasks/
├── provider-registry/          # Active task
│   ├── README.md              # Task overview
│   ├── design.md              # Specification
│   └── implementation.md      # Notes
├── wake-word-detection/        # Active task
│   └── README.md              # Simple task
└── archive/
    └── audio-format/          # Completed task
        └── README.md
```

### When Not to Archive
- Silence detection: Implementation complete but has known issues
- Provider registry: MVP complete but enhancements ongoing

## Questions to Ask

Before creating a task:
- Is this a bug fix, feature, or improvement?
- What priority level is appropriate?
- Does it need design documentation?

Before archiving:
- Are all issues resolved?
- Has key information been extracted?
- Are there follow-up tasks?

## Future Improvements

- Consider task templates for consistency
- Add task size estimates (S/M/L/XL)
- Track task dependencies
- Add completion dates to archived tasks

## Key Files

Global documentation in `docs/tasks/`:
- `README.md` - Task list and status tracker
- `implementation-notes.md` - Ongoing implementation decisions
- `key-insights.md` - Important learnings from all tasks
- `archive/` - Completed task directories
