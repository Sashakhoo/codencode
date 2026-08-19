# LMS UI Design System

## Source
The dashboard mockups are visual references only. They should guide layout, color, rhythm, spacing, cards, navigation, and responsive behavior. They must not replace existing LMS data, APIs, forms, routes, or business logic.

## Tokens
- Primary: `#0F9D58`
- Primary dark: `#0B7A43`
- Accent mint: `#10CDA7`
- Primary light background: `#E6F6EC`
- Page background: `#F0F1F3`
- Card: `#FFFFFF`
- Ink: `#14181B`
- Muted text: `#8A8F98`
- Muted secondary: `#B7BBC2`
- Border: `#ECEDEF`

## Shape
- Cards: `20px` radius
- Panels/modals: `22px-26px` radius
- Buttons/inputs: `12px-14px` radius
- Badges/tags: `8px-10px` radius or pill

## Typography
- Headings and key numbers: `Inter` or `Space Grotesk` style, bold and compact.
- Body: `Inter`.
- Data, money, status, short labels: `JetBrains Mono`.

## Layout Rules
- Use soft white cards on pale mint/gray backgrounds.
- Keep dashboard surfaces spacious, not compact or dark.
- Prefer a fixed sidebar on desktop and slide-in sidebar on mobile.
- Tables may scroll horizontally on small screens.
- Modals should become full-width and vertically scrollable on mobile.

## Logic Rule
Visual restyles must preserve existing function names, endpoints, form field IDs, state objects, and save/update behavior.
