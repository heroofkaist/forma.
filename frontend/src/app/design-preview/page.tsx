import { notFound } from 'next/navigation';
import { DesignViewport } from '../../components/design-viewport';
export default async function DesignPreview({searchParams}:{searchParams:Promise<{path?:string;width?:string}>}) {
  if(process.env.NODE_ENV!=='development') notFound();
  const {path='/',width}=await searchParams;
  if(!path.startsWith('/')||path.startsWith('//')||path.startsWith('/design-preview')||path.includes('\\')) notFound();
  return <DesignViewport path={path} initialWidth={[1440,768,390].includes(Number(width))?Number(width):1440}/>;
}
