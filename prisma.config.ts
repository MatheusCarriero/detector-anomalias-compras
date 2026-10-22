import { defineConfig } from "prisma/config";

// No .env loading or fallback target. validate/generate need no connection.
const url = process.env.DATABASE_URL;

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: { path: "prisma/migrations" },
  ...(url ? { datasource: { url } } : {}),
});
