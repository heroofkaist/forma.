import { API_URL, authenticatedFetch } from "./api";
import { platformRequest } from "./platform";

export type AssignmentTemplate = { id: string; file_name: string; required: boolean };
type Material = { id: string; file_name: string; tags: string; visibility: string };
const prefix = "forma:assignment-template:";
const MAX_BYTES = 30 * 1024 * 1024;

// Assignment attachments use the existing private course-material storage and access policy.
export function templateFromMaterials(items: Material[], assignmentId: string): AssignmentTemplate | null {
  for (const item of items) {
    if (item.visibility !== "student_visible") continue;
    if (item.tags === `${prefix}${assignmentId}:required` || item.tags === `${prefix}${assignmentId}:optional`) {
      return { id: item.id, file_name: item.file_name, required: item.tags.endsWith(":required") };
    }
  }
  return null;
}
export function templateFileError(file: File): string | null {
  if (!file.size) return "Выбранный файл пуст.";
  if (file.size > MAX_BYTES) return "Шаблон должен быть не больше 30 МБ.";
  if (!/\.(pdf|docx|pptx)$/i.test(file.name)) return "Выберите шаблон в формате PDF, DOCX или PPTX.";
  return null;
}
export async function loadAssignmentTemplate(offeringId: string, assignmentId: string) {
  const data = await platformRequest<{ items: Material[] }>(`/api/course-materials/${offeringId}`);
  return templateFromMaterials(data.items, assignmentId);
}
export async function uploadAssignmentTemplate(offeringId: string, assignmentId: string, file: File, required: boolean) {
  const error = templateFileError(file);
  if (error) throw new Error(error);
  // A retry after a lost response must not upload another attachment.
  const saved = await loadAssignmentTemplate(offeringId, assignmentId);
  if (saved) return saved;
  const data = new FormData();
  data.set("file", file); data.set("title", `Шаблон · ${file.name}`.slice(0, 200));
  data.set("visibility", "student_visible"); data.set("tags", `${prefix}${assignmentId}:${required ? "required" : "optional"}`);
  const response = await authenticatedFetch(`${API_URL}/api/course-materials/${offeringId}`, { method: "POST", body: data });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error("Не удалось сохранить шаблон. Повторите загрузку; задание уже создано.");
  return { id: String(body.id), file_name: file.name, required };
}
export async function copyAssignmentTemplate(sourceOfferingId: string, sourceId: string, offeringId: string, assignmentId: string) {
  const template = await loadAssignmentTemplate(sourceOfferingId, sourceId);
  if (!template) return;
  const response = await authenticatedFetch(`${API_URL}/api/materials/${template.id}/file`);
  if (!response.ok) throw new Error("Не удалось скопировать шаблон. Повторите попытку.");
  await uploadAssignmentTemplate(offeringId, assignmentId, new File([await response.blob()], template.file_name), template.required);
}
