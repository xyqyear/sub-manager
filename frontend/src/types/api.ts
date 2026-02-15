export type SubscriptionMode = "remote" | "manual";
export type RuleBehavior = "classical" | "domain" | "ipcidr";
export type GroupMode = "select" | "fallback" | "url-test";

export interface SubscriptionSource {
  id: string;
  name: string;
  mode: SubscriptionMode;
  enabled: boolean;
  remote_url: string | null;
  remote_auth_header: string | null;
  auto_update: boolean;
  update_interval_sec: number;
  next_refresh_at: string | null;
  last_refresh_at: string | null;
  last_status: string;
  last_error: string | null;
  subscription_userinfo_raw: string | null;
  subscription_userinfo_json: Record<string, number> | null;
  cached_proxies_json: Record<string, unknown>[] | null;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionSourceListItem {
  id: string;
  name: string;
  mode: SubscriptionMode;
  enabled: boolean;
  remote_url: string | null;
  remote_auth_header: string | null;
  auto_update: boolean;
  update_interval_sec: number;
  next_refresh_at: string | null;
  last_refresh_at: string | null;
  last_status: string;
  last_error: string | null;
  subscription_userinfo_raw: string | null;
  subscription_userinfo_json: Record<string, number> | null;
  cached_proxies_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface RuleSource {
  id: string;
  name: string;
  mode: SubscriptionMode;
  behavior: RuleBehavior;
  enabled: boolean;
  remote_url: string | null;
  auto_update: boolean;
  update_interval_sec: number;
  next_refresh_at: string | null;
  last_refresh_at: string | null;
  last_status: string;
  last_error: string | null;
  cached_payload_lines_json: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface RuleSourceListItem {
  id: string;
  name: string;
  mode: SubscriptionMode;
  behavior: RuleBehavior;
  enabled: boolean;
  remote_url: string | null;
  auto_update: boolean;
  update_interval_sec: number;
  next_refresh_at: string | null;
  last_refresh_at: string | null;
  last_status: string;
  last_error: string | null;
  cached_payload_lines_count: number | null;
  created_at: string;
  updated_at: string;
}

export interface MainConfig {
  id: string;
  name: string;
  base_config_yaml: string;
  enabled: boolean;
  final_target_type: "DIRECT" | "REJECT" | "group";
  final_target_group_name: string | null;
  filtered_groups: {
    name: string;
    position: number;
    group_mode: GroupMode;
    test_url?: string | null;
    test_interval_sec?: number | null;
    copy_nodes?: boolean;
    rules: {
      subscription_source_id: string;
      regex_pattern: string;
      regex_flags: string;
      position: number;
    }[];
  }[];
  manual_groups: {
    name: string;
    position: number;
    group_mode: GroupMode;
    test_url?: string | null;
    test_interval_sec?: number | null;
    members: {
      member_type: "filtered_group" | "manual_group";
      member_ref: string;
      position: number;
    }[];
  }[];
  dialer_override_rules: {
    filtered_group_name: string;
    dialer_group_name: string;
  }[];
  route_bindings: {
    position: number;
    binding_name: string;
    rule_source_id: string;
    default_group_name: string;
    no_resolve: boolean;
  }[];
  created_at: string;
  updated_at: string;
}

export interface PreviewResponse {
  yaml: string;
  diagnostics: {
    stale_subscription_ids: string[];
    stale_rule_ids: string[];
    warnings: string[];
  };
}

export interface FilteredGroupPreviewRuleResult {
  matched_proxy_names: string[];
  issue: string | null;
}

export interface FilteredGroupPreviewItem {
  name: string;
  rule_results: FilteredGroupPreviewRuleResult[];
}

export interface FilteredGroupPreviewResponse {
  groups: FilteredGroupPreviewItem[];
}
