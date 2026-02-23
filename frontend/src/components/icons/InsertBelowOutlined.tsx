import Icon from "@ant-design/icons";
import type { CustomIconComponentProps } from "@ant-design/icons/lib/components/Icon";

const Svg = () => (
  <svg width="1em" height="1em" fill="currentColor" viewBox="64 64 896 896">
    <path d="M316 744L442 544h-90V164h-72v380h-90L316 744z" />
    <path d="M684 274h48v360h-48z" />
    <path d="M528 430h360v48H528z" />
    <path d="M160 832h704q8 0 8 8v48q0 8-8 8H160q-8 0-8-8v-48q0-8 8-8z" />
  </svg>
);

const InsertBelowOutlined = (props: Partial<CustomIconComponentProps>) => (
  <Icon component={Svg} {...props} />
);

export default InsertBelowOutlined;
