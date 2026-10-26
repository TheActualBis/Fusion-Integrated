import js from "@eslint/js";

export default [
    {
        ignores: ["dist/**", "node_modules/**", "**/dist/**", "**/node_modules/**"]
    },
    js.configs.recommended,
    {
        rules: {
            "no-unused-vars": "warn",
            "no-undef": "warn"
        }
    }
];
