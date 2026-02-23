import Icon from "@ant-design/icons";
import type { CustomIconComponentProps } from "@ant-design/icons/lib/components/Icon";

const Svg = () => (
  <svg width="1em" height="1em" fill="currentColor" viewBox="64 64 896 896">
    <path d="M160 128h704q8 0 8 8v48q0 8-8 8H160q-8 0-8-8v-48q0-8 8-8z" />
    <path d="M316 280L190 480h90v380h72V480h90L316 280z" />
    <path d="M684 390h48v360h-48z" />
    <path d="M528 546h360v48H528z" />
  </svg>
);

const InsertAboveOutlined = (props: Partial<CustomIconComponentProps>) => (
  <Icon component={Svg} {...props} />
);

export default InsertAboveOutlined;
