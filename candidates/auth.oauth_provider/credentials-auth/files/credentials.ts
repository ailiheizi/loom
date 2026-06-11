import CredentialsProvider from "next-auth/providers/credentials";

/**
 * 账号密码登录 provider（NextAuth v5 Credentials）。
 * 非 OAuth：用户用邮箱+密码登录。authorize 里校验凭据（这里给最小骨架，
 * 真实项目应查库 + 比对 hash）。接入 authConfig.providers[]。
 */
export const credentialsProvider = CredentialsProvider({
  name: "Credentials",
  credentials: {
    email: { label: "Email", type: "email" },
    password: { label: "Password", type: "password" },
  },
  authorize(credentials: Record<string, unknown> | undefined) {
    const email = credentials?.email;
    const password = credentials?.password;
    if (typeof email !== "string" || typeof password !== "string") {
      return null;
    }
    if (email.length === 0 || password.length === 0) {
      return null;
    }
    // 最小骨架：真实项目在此查库 + 比对密码 hash。
    return { id: email, email, name: email.split("@")[0] ?? email };
  },
});
