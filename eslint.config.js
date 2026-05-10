import globals from "globals";

export default [
  {
    ignores: ["frontend/vendor/**"]
  },
  {
    files: ["frontend/**/*.js"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: {
        ...globals.browser,
        Vue: "readonly"
      }
    },
    rules: {
      "no-undef": "error",
      "no-unreachable": "error",
      "no-redeclare": "error"
    }
  }
];
