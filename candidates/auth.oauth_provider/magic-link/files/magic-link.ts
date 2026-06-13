import CredentialsProvider from "next-auth/providers/credentials";

/**
 * Magic-link 风格的邮箱登录 provider（用 Credentials 实现，零外部依赖）。
 * 接收邮箱 + 一次性验证码，校验通过即登录。加入 authConfig.providers[]。
 * 注：生产需接真实邮件发送 + 验证码存储；此处为可编译的骨架（验证码校验留 TODO）。
 */
export const magicLinkProvider = CredentialsProvider({
  id: "magic-link",
  name: "邮箱登录",
  credentials: {
    email: { label: "邮箱", type: "email" },
    code: { label: "验证码", type: "text" },
  },
  authorize(credentials) {
    const email = credentials?.email;
    const code = credentials?.code;
    if (typeof email !== "string" || typeof code !== "string") {
      return null;
    }
    // TODO: 校验 code 与发送记录是否匹配（接邮件服务后实现）
    if (code.length < 4) {
      return null;
    }
    return { id: email, email, name: email.split("@")[0] ?? email };
  },
});
