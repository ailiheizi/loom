/**
 * 本地 data-URL 上传：把 File 读成 base64 data URL，返回可直接用作 src 的 URL。
 * 零依赖、零后端，适合 MVP/预览（图片头像等小文件）。不持久化、不适合大文件。
 */
export async function uploadFile(file: File): Promise<{ url: string }> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(new Error("读取文件失败"));
    reader.readAsDataURL(file);
  });
  return { url: dataUrl };
}
