# Release Notes

> Release summaries and upgrade guides for C.E.H. (Core Engine Hub).

## How to Use These Notes

Release notes provide a **user-friendly summary** of each version. For detailed technical changes, see [`CHANGELOG.md`](CHANGELOG.md).

---

## Version X.Y.Z (YYYY-MM-DD)

> **Status**: Template — not yet released

### Summary

[Brief summary of this release. Example: "First stable release of C.E.H. with core agent engine, memory system, and CLI interface."]

### Highlights

- Key feature 1
- Key feature 2
- Key feature 3

### Breaking Changes

- [if any — describe migration path]

### Upgrade Instructions

- [if any — describe steps to upgrade safely]

### Full Changelog

See [`CHANGELOG.md`](CHANGELOG.md) for the complete list of changes.

---

## Template: Creating New Release Notes

When preparing a new release, copy this template and fill in the sections:

```markdown
## Version X.Y.Z (YYYY-MM-DD)

### Summary
[One-paragraph summary of what this release delivers.]

### Highlights
- [Feature]: [Brief description]
- [Feature]: [Brief description]
- [Improvement]: [Brief description]
- [Fix]: [Brief description]

### Breaking Changes
[Describe any breaking changes and how to migrate. Omit if none.]

### Upgrade Instructions
[Describe any special steps needed to upgrade. Omit if standard `uv sync` suffices.]

### Known Issues
[List any known issues in this release. Omit if none.]

### Full Changelog
[Link to CHANGELOG.md entries for this version.]
```

---

## Release Checklist

Before publishing release notes:

- [ ] All CHANGELOG.md entries verified
- [ ] Version number matches `pyproject.toml`
- [ ] Breaking changes documented with migration path
- [ ] Upgrade instructions tested
- [ ] Screenshots/gifs updated (if applicable)
- [ ] Links to CHANGELOG.md verified
- [ ] License year updated (if applicable)
