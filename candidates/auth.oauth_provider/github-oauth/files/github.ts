import GitHubProvider from "next-auth/providers/github";

import { env } from "~/env";

/**
 * 配置好的 GitHub OAuth provider，加入 authConfig.providers[]。
 * 需要环境变量 AUTH_GITHUB_ID / AUTH_GITHUB_SECRET。
 */
export const githubProvider = GitHubProvider({
  clientId: env.AUTH_GITHUB_ID,
  clientSecret: env.AUTH_GITHUB_SECRET,
});
