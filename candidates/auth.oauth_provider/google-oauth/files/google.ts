import GoogleProvider from "next-auth/providers/google";

import { env } from "~/env";

/**
 * 配置好的 Google OAuth provider，加入 authConfig.providers[]。
 * 需要环境变量 AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET。
 */
export const googleProvider = GoogleProvider({
  clientId: env.AUTH_GOOGLE_ID,
  clientSecret: env.AUTH_GOOGLE_SECRET,
});
