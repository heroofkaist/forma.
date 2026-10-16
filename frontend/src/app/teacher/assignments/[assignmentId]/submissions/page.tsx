"use client";
import {useParams} from 'next/navigation';
import {AppShell} from '../../../../../components/app-shell';
import {AssignmentWorkspace} from '../../../../../components/assignment/assignment-workspace';
export default function SubmissionsPage(){
  const {assignmentId}=useParams<{assignmentId:string}>();
  return <AppShell><AssignmentWorkspace key={assignmentId} assignmentId={assignmentId}/></AppShell>;
}
