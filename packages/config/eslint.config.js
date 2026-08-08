// Shared rule overrides layered on top of each app's own framework preset
// (e.g. `eslint-config-next` in apps/web), so cross-cutting conventions are
// defined once instead of duplicated per app. Deliberately does not bundle a
// full recommended ruleset of its own — the consuming app's framework
// config already provides that, and re-declaring it here risks conflicting
// with framework-specific parser/plugin wiring.

/** @type {import("eslint").Linter.Config[]} */
module.exports = [
  {
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/consistent-type-imports": "warn",
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },
  {
    ignores: ["dist/**", ".next/**", "node_modules/**"],
  },
];
