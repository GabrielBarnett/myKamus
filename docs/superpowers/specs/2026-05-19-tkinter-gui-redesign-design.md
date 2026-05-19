# Tkinter GUI Redesign Design

## Goal

Replace the PySide6 desktop GUI with a Tkinter-based GUI that ships with Python, while preserving myKamus's current user-facing capabilities and improving the overall layout, structure, and maintainability of the application.

## User Outcome

A user launches myKamus with the same entry points they use today:

- `Start myKamus.bat`
- `python -m gui_app.app`

The app opens into a calmer, less crowded lookup experience that still supports manual search, clipboard-driven search, indexing, history, compact mode, always-on-top behavior, and responsive resizing. The GUI no longer depends on PySide6 or any other third-party GUI toolkit.

## Scope

Included:

- Full replacement of the PySide6 GUI with a Tkinter/`ttk` GUI.
- Full feature parity for the current GUI behavior.
- A calmer, search-first layout redesign.
- Broader internal restructuring to create cleaner boundaries between UI, state, and services.
- Cross-platform GUI design for Windows, macOS, and Linux.
- Preservation of existing entry points, config conventions, and data-folder behavior.
- README and developer-documentation updates for the Tkinter architecture.
- Removal of PySide6 as a GUI dependency once parity is reached.

Excluded:

- Rewriting search or indexing algorithms unless interface cleanup requires light adaptation.
- Changing dictionary content, result ordering, or lookup semantics.
- Bundling Python, building an installer, or introducing a custom executable.
- Replacing non-GUI third-party libraries solely to pursue standard-library purity outside the GUI layer.
- Packaging redesign beyond what is needed to stop requiring PySide6 for the GUI.

## Design Principles

- Keep the app recognizable to current users even though the layout becomes calmer.
- Use Tkinter because it ships with Python, not because the app should look primitive.
- Favor clean module boundaries over a one-file widget port.
- Preserve user-facing launch behavior and stored settings.
- Treat cross-platform behavior as a first-class requirement, not a later cleanup task.
- Use standard-library GUI tools only: `tkinter`, `ttk`, `tkinter.messagebox`, `tkinter.filedialog`, `tkinter.scrolledtext`, and related built-in modules.

## Architecture

`gui_app/app.py` remains the stable entry point for `python -m gui_app.app`, but it should become a thin launcher that boots the Tkinter application rather than containing most of the GUI behavior directly.

The redesigned GUI should be split into layers with clear responsibilities:

- `gui_app/core/`
  - application state model
  - config/history persistence
  - search request orchestration
  - indexing coordination
  - clipboard and status behavior
  - result shaping for display
- `gui_app/runtime/`
  - background task runner based on `threading`, `queue`, and cancellation flags
  - main-thread handoff helpers for Tkinter `after()` processing
  - shutdown coordination for in-flight tasks
- `gui_app/tk/`
  - root window and layout composition
  - reusable `ttk` widget compositions
  - dialogs, menus, status strip, tools panel, and results rendering
  - keyboard bindings and focus behavior

The core layer must not depend on Tkinter widget classes. It should expose application operations and state transitions that the Tkinter layer consumes. This keeps the new architecture easier to test and avoids repeating the current pattern where UI framework details and application behavior are tightly interwoven.

## UI Structure And Layout

The Tkinter redesign should adopt the calmer direction already validated during brainstorming: a search-first reader layout with secondary tools moved out of the main visual path.

Default layout:

1. Top command strip with:
   - primary search entry
   - visible `Search` action
   - quiet `Tools` toggle
2. Slim status line for clipboard-monitoring state, indexing state, and short feedback messages.
3. Small inline recent-search row for the last few queries.
4. Single scrolling results surface in this order:
   - Red Book Results
   - Word Translations
   - Example Sentences
5. Hidden-by-default tools panel containing:
   - clipboard details
   - monitoring controls
   - always-on-top toggle
   - compact mode toggle
   - fuller recent-search list
   - secondary actions such as `Load All`

At narrow widths, the window should remain single-column and the tools surface should behave like a drawer, pop-out panel, or other collapsible side area rather than a permanently visible sidebar. At medium widths, the same structure should simply gain breathing room rather than shifting into a dashboard-like composition.

Results should read like dictionary entries rather than stacked control cards. Section headers should be quieter, separators lighter, and repeated entry layouts more text-forward. Persistent visual noise should be minimized.

## Feature Parity And Behavior

The first Tkinter release is not a reduced shell. It should preserve the important current behaviors:

- manual search
- `Search`, `Clear`, and `Load All`
- clipboard monitoring with automatic lookup
- always-on-top support
- compact mode
- recent search history
- first-run indexing and indexing feedback
- responsive narrow-window behavior
- current config and data-folder conventions
- current result ordering and lookup semantics

Parity should be measured at the behavior level, not at the widget-for-widget level. The new UI does not need to preserve the current layout or PySide6 implementation patterns. It does need to preserve the app's practical usefulness for people who already rely on it.

Copy behavior should become lighter than the current always-visible button-heavy presentation. The default interaction should favor selection, keyboard shortcuts, and limited contextual affordances over persistent per-item controls everywhere on screen.

## Concurrency, State, And Error Handling

The Tkinter main thread should only handle rendering, input, and scheduled polling. Long-running work such as indexing, sentence expansion, and slower searches should run in background threads.

Concurrency model:

- background work runs in `threading.Thread` workers
- workers send structured messages to a thread-safe `queue.Queue`
- the Tkinter UI drains the queue on a short `after()` cadence
- cancellation is handled through task ownership, cancellation flags, and stale-result suppression

The GUI should track explicit application state instead of hiding behavior inside widget state. At minimum, state should cover:

- current query
- current clipboard value
- monitoring enabled/disabled
- indexing status
- active search task identity
- compact mode
- always-on-top state
- recent-search history
- current rendered result payload
- tools panel visibility

Shutdown behavior must be explicit. When the window closes, the app should stop clipboard polling, stop or mark background work for cancellation where practical, ignore stale worker messages, persist config/history, and then destroy the Tkinter root cleanly. The design should prevent the equivalent of the earlier Qt worker-teardown problem.

Error surfaces should be layered:

- inline status text for routine transient issues
- modal dialogs for blocking failures such as missing data or indexing failure
- terminal and log output for troubleshooting details

## Styling, Theming, And Tkinter Constraints

The GUI should aim for a modern utility-app feel, not a toy demo and not an imitation web app.

Styling strategy:

- central theme module for colors, spacing, fonts, and shared geometry constants
- `ttk.Style` as the primary styling mechanism
- `clam` as the default styling baseline where available because it is more controllable across platforms than fully native themes
- reusable composed widgets for repeated UI patterns such as section headers, result rows, status strip blocks, recent-query items, and tools-panel sections
- minimal custom drawing, used only where `ttk` cannot express an important part of the design cleanly

The design should rely on disciplined spacing, alignment, typography, and grouping rather than on heavy decorative styling. Hover and focus behavior should be improved where Tkinter supports it cleanly, but the spec should not depend on fragile theming tricks.

Tkinter constraints should be treated honestly:

- styling flexibility is lower than Qt's
- some visual behavior varies by platform
- more polished controls may need composite widgets rather than a single styled built-in widget
- responsive behavior must come from layout discipline, not advanced framework abstractions

The visual target is a polished, efficient desktop utility that happens to be built with Tkinter, not a clone of the previous Qt skin.

## Cross-Platform Behavior

Windows, macOS, and Linux should all remain first-class targets.

Cross-platform design requirements:

- avoid styling choices that depend on a single platform's widget behavior
- isolate platform-specific window behaviors such as always-on-top and clipboard edge cases behind small helpers
- use geometry, spacing, and font choices that remain readable across DPI differences
- keep keyboard navigation and focus handling explicit rather than assuming platform defaults are good enough

Where a behavior cannot be perfectly identical across platforms, the implementation should standardize the user-visible outcome as much as possible and document any known platform-specific limitations.

## Entry Points, Dependencies, And Migration Boundary

User-facing entry points must remain stable:

- `Start myKamus.bat`
- `python -m gui_app.app`

Config locations, data-folder behavior, and the existing Windows dependency preflight flow should remain intact unless a change is necessary to remove PySide6-specific assumptions.

This redesign should also update the GUI dependency story:

- the GUI must no longer require PySide6
- `README.md` should stop describing the app as a PySide6 GUI
- any import guard or launcher/preflight messaging that currently names PySide6 as required for the GUI should be revised
- requirements and dependency checks should reflect the new Tkinter-based GUI surface

The Windows local dependency workflow remains valuable for non-GUI packages, but the GUI itself should stop depending on third-party toolkit installation.

## Testing Strategy

Testing should shift away from treating the GUI file as the main unit of confidence.

Primary test layers:

- unit tests for core state transitions and service behavior
- focused tests for config persistence, search history, clipboard-related state logic, and result shaping
- runtime tests for queue-driven background task updates, stale-result suppression, and shutdown behavior
- smaller GUI tests that verify Tkinter wiring, visible state changes, and key layout toggles without overfitting to pixel details

Manual smoke tests should cover:

- first launch with indexing
- manual search flow
- clipboard-driven automatic lookup
- compact mode
- always-on-top behavior
- narrow-window layout
- recent-search interactions
- shutdown during active background work
- behavior on Windows, macOS, and Linux

## Documentation

Update `README.md` and developer-facing docs to explain:

- Tkinter now powers the GUI
- no third-party GUI toolkit is required
- the launch commands remain unchanged
- the new internal module layout under `gui_app/`
- any updated troubleshooting guidance for GUI startup and platform-specific behavior

The implementation plan should also include cleanup of obsolete PySide6-specific tests, docs, and code once the Tkinter path reaches parity, so the repository does not keep two half-alive GUI architectures.

## Risks And Trade-Offs

- A full replacement plus broader restructure is larger than a simple widget port.
- Tkinter can feel dated if styling discipline slips, so layout and widget composition matter more than usual.
- Some PySide6 conveniences, especially richer widget styling and thread signaling, will need more explicit application code in Tkinter.
- Cross-platform polish will require deliberate testing because Tkinter renders differently across operating systems.

These trade-offs are acceptable because the project goal is not just visual cleanup. It is to remove the third-party GUI dependency while ending up with a cleaner, more maintainable desktop app.

## Future Work

This redesign should stand on its own as the full GUI migration. Later work can build on it with additional packaging or installer exploration, but those concerns should not be folded into this spec.
