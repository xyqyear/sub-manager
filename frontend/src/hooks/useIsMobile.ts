import { Grid } from "antd";

export default function useIsMobile(): boolean {
  const screens = Grid.useBreakpoint();
  return !screens.md;
}
