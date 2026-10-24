Fonts embedded in generated PDF reports and used for the report's charts and flowcharts.
All are SIL Open Font License 1.1 (https://openfontlicense.org), from Google Fonts via the
@fontsource npm packages (v5.1.0). Each file merges the "latin" and "latin-ext" subsets.

- Fraunces (Regular, SemiBold, Italic, SemiBold Italic) – headings and large italic statements.
- DM Sans (Regular, Italic, Bold) – body text, descriptions, captions, chart text.
- DM Mono (Regular, Medium) – small uppercase labels, tags, table headers, page metadata.
- DM Sans and Fraunces include the ₹ sign; DM Mono does not, so ₹ in labels falls back to DM Sans.
- Remaining symbols (e.g. ☐) fall back to DejaVu Sans, bundled with matplotlib.

Felipa-Regular.ttf (Fontstage, SIL OFL) is present but not referenced by the report.
