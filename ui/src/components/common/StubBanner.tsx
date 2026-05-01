/**
 * Banner shown on pages where some or all of the displayed values are not
 * yet derived from a real pipeline run. Keeps the user (and AI auditor)
 * honest about which numbers can be trusted.
 */
export default function StubBanner({
  fields,
  note,
}: {
  fields?: readonly string[];
  note?: string;
}) {
  return (
    <div className="bg-warn/10 border border-warn/40 rounded p-2 mb-3 text-[11px] text-warn">
      <span className="font-semibold">⚠ Заглушка на этой странице.</span>{" "}
      {note ?? "Отображаемые значения — детерминированные заглушки, а не реальный вывод пайплайна."}
      {fields && fields.length > 0 && (
        <span> Поля-заглушки: <span className="font-mono">{fields.join(", ")}</span>.</span>
      )}
    </div>
  );
}
