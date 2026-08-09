# Bicep Composition Service

Local .NET sidecar for compiler-assisted Bicep composition using `Azure.Bicep.Core`.

This project exposes a stable local HTTP contract for the Python backend. Parsing and diagnostic validation are compiler-backed, and Stage 5 composition behavior is now validated for typed contracts, fragment identity preservation, exact-match dedupe, deterministic param/var rename handling, rename-aware declaration rewriting, unresolved reference reporting, and generated package output. Broader composition migration can still continue incrementally as later stages move additional merge paths away from regex/string transforms.