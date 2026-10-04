export type SuggestedPrompt = {
  id: string;
  label: string;
  text: string;
  enabled: boolean;
};
export const suggestedPrompts: SuggestedPrompt[] = [
  {
    id: "pen",
    label: "เลือกปากกา",
    text: "ช่วยแนะนำปากกาสำหรับจดโน้ตทุกวัน พร้อมอธิบายวิธีเลือก",
    enabled: true,
  },
  {
    id: "notebook",
    label: "เลือกสมุด",
    text: "สมุดแบบไหนเหมาะกับการจดเลกเชอร์และใช้ไฮไลต์?",
    enabled: true,
  },
  {
    id: "starter",
    label: "หาเครื่องเขียน",
    text: "ช่วยแนะนำเครื่องเขียนพื้นฐานสำหรับเริ่มเรียนมหาวิทยาลัย",
    enabled: true,
  },
];
