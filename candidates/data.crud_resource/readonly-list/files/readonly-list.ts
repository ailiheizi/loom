import { createTRPCRouter, protectedProcedure } from "~/server/api/trpc";
import { db } from "~/server/db";
import { z } from "zod";

/**
 * 只读列表 router（list + get，无写操作）。
 * 适合"只展示不编辑"的资源（如公告、日志、报表条目）。比全 CRUD 更轻，
 * 也更安全（无 mutation）。绑定 db.project（复用 Project model）。
 */
export const readonlyListRouter = createTRPCRouter({
  list: protectedProcedure.query(() => {
    return db.project.findMany({ orderBy: { createdAt: "desc" } });
  }),
  get: protectedProcedure
    .input(z.object({ id: z.string() }))
    .query(({ input }) => {
      return db.project.findUnique({ where: { id: input.id } });
    }),
});
