export function assignmentPreflight(form: {title:string; maximum_score:string; available_at:string; due_at:string}, criteria: {description:string; maximum_points:string}[]) {
  const errors:string[]=[];const warnings:string[]=[];
  const maximum=Number(form.maximum_score);
  if(!form.title.trim())errors.push('Укажите название задания.');
  if(!Number.isFinite(maximum) || maximum<=0 || maximum>10000)errors.push('Максимальный балл должен быть больше 0 и не больше 10000.');
  const active=criteria.filter(c=>c.description.trim());
  if(active.some(c=>!Number.isFinite(Number(c.maximum_points)) || Number(c.maximum_points)<=0 || Number(c.maximum_points)>10000))errors.push('У каждого критерия должен быть положительный конечный максимум.');
  const total=active.reduce((sum,c)=>sum+Number(c.maximum_points),0);
  if(total>maximum+1e-8)errors.push('Сумма критериев превышает максимум задания.');
  else if(active.length && total<maximum-1e-8)warnings.push('Сумма критериев меньше максимума: проверьте, где начисляются оставшиеся баллы.');
  if(!active.length)warnings.push('Явные критерии не заполнены. Проверьте общую рубрику перед началом оценивания.');
  const available=form.available_at?Date.parse(form.available_at):null,due=form.due_at?Date.parse(form.due_at):null;
  if((available!==null&&!Number.isFinite(available)) || (due!==null&&!Number.isFinite(due)))errors.push('Проверьте даты открытия и сдачи.');
  if(available!==null && due!==null && due<=available)errors.push('Срок сдачи должен быть позже открытия задания.');
  return {errors,warnings,total};
}
