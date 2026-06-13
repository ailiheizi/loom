/**
 * 预签名 URL 上传：把文件 PUT 到调用方提供的预签名 URL（S3/R2/OSS 常见模式），
 * 返回去掉 query 的可访问 URL。零依赖（浏览器原生 fetch）。
 * 需调用方先拿到 presignedUrl（由后端签发）；本函数只负责上传动作。
 */
export async function uploadFile(
  file: File,
  presignedUrl: string,
): Promise<{ url: string }> {
  const resp = await fetch(presignedUrl, {
    method: "PUT",
    body: file,
    headers: { "Content-Type": file.type || "application/octet-stream" },
  });
  if (!resp.ok) {
    throw new Error(`上传失败 HTTP ${resp.status}`);
  }
  const url = presignedUrl.split("?")[0] ?? presignedUrl;
  return { url };
}
