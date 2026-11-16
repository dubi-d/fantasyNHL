import openapiTS, { astToString, COMMENT_HEADER } from "openapi-typescript";
import { expect, test } from "vitest";

import spec from "../openapi.json?raw";
import generated from "./schema.d.ts?raw";

test("the generated API types match the committed API schema", async () => {
  // out of date? `npm run types` (after UPDATE_OPENAPI=1 pytest, see README)
  const ast = await openapiTS(JSON.parse(spec));
  expect(COMMENT_HEADER + astToString(ast)).toBe(generated);
}, 30_000);
