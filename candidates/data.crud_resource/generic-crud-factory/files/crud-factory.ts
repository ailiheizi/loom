import { z } from "zod";

import { createTRPCRouter, protectedProcedure } from "~/server/api/trpc";
import { db } from "~/server/db";

type CrudModel = {
  findMany: (args: { orderBy: { createdAt: "desc" } }) => Promise<unknown>;
  findUnique: (args: { where: { id: string } }) => Promise<unknown>;
  create: (args: {
    data: { name: string; description?: string | undefined };
  }) => Promise<unknown>;
  update: (args: {
    where: { id: string };
    data: { name?: string | undefined; description?: string | undefined };
  }) => Promise<unknown>;
  delete: (args: { where: { id: string } }) => Promise<unknown>;
};

const createInput = z.object({
  name: z.string().min(1),
  description: z.string().min(1).optional(),
});

const updateInput = z.object({
  id: z.string(),
  name: z.string().min(1).optional(),
  description: z.string().min(1).optional(),
});

export const createCrudRouter = (model: CrudModel) =>
  createTRPCRouter({
    list: protectedProcedure.query(async () => {
      return model.findMany({
        orderBy: { createdAt: "desc" },
      });
    }),

    get: protectedProcedure
      .input(z.object({ id: z.string() }))
      .query(async ({ input }) => {
        return model.findUnique({
          where: { id: input.id },
        });
      }),

    create: protectedProcedure
      .input(createInput)
      .mutation(async ({ input }) => {
        return model.create({
          data: {
            name: input.name,
            description: input.description,
          },
        });
      }),

    update: protectedProcedure
      .input(updateInput)
      .mutation(async ({ input }) => {
        const { id, ...data } = input;

        return model.update({
          where: { id },
          data,
        });
      }),

    delete: protectedProcedure
      .input(z.object({ id: z.string() }))
      .mutation(async ({ input }) => {
        return model.delete({
          where: { id: input.id },
        });
      }),
  });

// 用 db 单例（模块级，非请求期 ctx）绑定具体 model，导出成品 router。
// 注册进 appRouter 时直接引用此成品（project: projectRouter），不在 root.ts 顶层调工厂——
// 顶层没有 ctx，createCrudRouter(ctx.db.x) 会 TS2304。
export const projectRouter = createCrudRouter(db.project);
