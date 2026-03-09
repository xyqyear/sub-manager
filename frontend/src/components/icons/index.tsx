import type { SVGProps } from "react";

export function InsertAboveOutlined(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" {...props}>
      <path d="M160 128h704q8 0 8 8v48q0 8-8 8H160q-8 0-8-8v-48q0-8 8-8z" />
      <path d="M316 280L190 480h90v380h72V480h90L316 280z" />
      <path d="M684 390h48v360h-48z" />
      <path d="M528 546h360v48H528z" />
    </svg>
  );
}

export function InsertBelowOutlined(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" {...props}>
      <path d="M316 744L442 544h-90V164h-72v380h-90L316 744z" />
      <path d="M684 274h48v360h-48z" />
      <path d="M528 430h360v48H528z" />
      <path d="M160 832h704q8 0 8 8v48q0 8-8 8H160q-8 0-8-8v-48q0-8 8-8z" />
    </svg>
  );
}
