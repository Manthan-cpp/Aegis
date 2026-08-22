"use client";

export type SOSImageShareResult = "shared" | "downloaded" | "cancelled";
export type SOSMessageShareResult = "shared" | "copied" | "cancelled";

const SOS_IMAGE_FILENAME = "aegis-sos.png";

function canUseFileShare(file: File): boolean {
  if (typeof navigator === "undefined" || typeof File === "undefined") return false;
  if (typeof navigator.share !== "function" || typeof navigator.canShare !== "function") return false;

  try {
    return navigator.canShare({ files: [file] });
  } catch {
    return false;
  }
}

/** Detect file-sharing support without relying on user-agent sniffing. */
export function canShareSOSImage(): boolean {
  if (typeof File === "undefined") return false;
  const probe = new File(["aegis"], SOS_IMAGE_FILENAME, { type: "image/png" });
  return canUseFileShare(probe);
}

/** Detect text-sharing support without relying on user-agent sniffing. */
export function canShareSOSMessage(): boolean {
  return typeof navigator !== "undefined" && typeof navigator.share === "function";
}

function downloadSOSImage(imageBlob: Blob): void {
  const objectUrl = URL.createObjectURL(imageBlob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = SOS_IMAGE_FILENAME;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

/**
 * Open the native share sheet with the original PNG attached.
 *
 * The optional number is intentionally not inserted into share text: browser
 * share sheets cannot reliably choose an SMS recipient, so the user selects
 * the trusted contact inside their Messages app.
 */
export async function shareSOSImage(
  imageBlob: Blob,
  trustedContactNumber?: string,
): Promise<SOSImageShareResult> {
  void trustedContactNumber;

  if (typeof window === "undefined" || typeof File === "undefined") {
    downloadSOSImage(imageBlob);
    return "downloaded";
  }

  const file = new File([imageBlob], SOS_IMAGE_FILENAME, {
    type: imageBlob.type || "image/png",
  });

  if (!canUseFileShare(file)) {
    downloadSOSImage(imageBlob);
    return "downloaded";
  }

  try {
    await navigator.share({
      files: [file],
      title: "",
      text: "",
    });
    return "shared";
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") return "cancelled";
    throw error;
  }
}

/**
 * Share a user-written message through the native share sheet.
 *
 * If the browser cannot open a native share sheet, copy the message so the
 * user can paste it into Messages without adding an SMS URI or dependency.
 */
export async function shareSOSMessage(
  message: string,
  trustedContactNumber?: string,
): Promise<SOSMessageShareResult> {
  void trustedContactNumber;
  const cleanMessage = message.trim();
  if (!cleanMessage) throw new Error("Enter a custom message first.");

  if (canShareSOSMessage()) {
    try {
      await navigator.share({ title: "", text: cleanMessage });
      return "shared";
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return "cancelled";
      throw error;
    }
  }

  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(cleanMessage);
    return "copied";
  }

  throw new Error("Text sharing is unavailable in this browser.");
}
