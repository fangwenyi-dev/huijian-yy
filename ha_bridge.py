#!/usr/bin/env python3
"""
Home Assistant MCP Bridge Script
用于 Trae IDE 与 Home Assistant 之间的桥接调试工具
"""

import os
import sys
import json
import argparse
from typing import Optional, Any

HA_URL = os.environ.get("HA_URL", "http://192.168.1.91:8123/")
HA_TOKEN = os.environ.get("HA_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJhMmM0MGU1MDJhODY0ZDcwYjBiNjMwMGQwOGViY2U1NSIsImlhdCI6MTc3MTkyNDIyNywiZXhwIjoyMDg3Mjg0MjI3fQ.VOtxhZ9tN02F3445UKPESTCVRi-zxzwk93L1GCoFAqs")

HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json"
}

def parse_args():
    parser = argparse.ArgumentParser(description="HA MCP Bridge - Home Assistant Debug Tool")
    parser.add_argument("--url", default=HA_URL, help="Home Assistant URL")
    parser.add_argument("--token", default=HA_TOKEN, help="Long-Lived Access Token")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    subparsers.add_parser("states", help="Get all entity states")
    subparsers.add_parser("services", help="List all services")
    subparsers.add_parser("config", help="Get HA config")
    
    entity_parser = subparsers.add_parser("state", help="Get specific entity state")
    entity_parser.add_argument("entity_id", help="Entity ID (e.g., light.living_room)")
    
    service_parser = subparsers.add_parser("call", help="Call a service")
    service_parser.add_argument("domain", help="Service domain (e.g., light)")
    service_parser.add_argument("service", help="Service name (e.g., turn_on)")
    service_parser.add_argument("--entity-id", help="Target entity ID")
    service_parser.add_argument("--data", help="JSON data for service call")
    
    subparsers.add_parser("events", help="List event types")
    
    return parser.parse_args()

def http_request(method: str, endpoint: str, data: Optional[dict] = None) -> dict:
    """Send HTTP request to Home Assistant"""
    import urllib.request
    import urllib.error
    
    url = f"{HA_URL}{endpoint.lstrip('/')}"
    request_data = json.dumps(data).encode() if data else None
    
    req = urllib.request.Request(url, data=request_data, headers=HEADERS, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read()
            return {
                "status": response.status,
                "data": json.loads(content.decode()) if content else {}
            }
    except urllib.error.HTTPError as e:
        return {
            "status": e.code,
            "error": e.read().decode() if e.fp else str(e)
        }
    except Exception as e:
        return {"error": str(e)}

def cmd_states():
    """Get all entity states"""
    result = http_request("GET", "/api/states")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result

def cmd_services():
    """List all services"""
    result = http_request("GET", "/api/services")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result

def cmd_config():
    """Get HA config"""
    result = http_request("GET", "/api/config")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result

def cmd_state(entity_id: str):
    """Get specific entity state"""
    result = http_request("GET", f"/api/states/{entity_id}")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result

def cmd_call(domain: str, service: str, entity_id: Optional[str] = None, data: Optional[str] = None):
    """Call a service"""
    payload = {}
    if entity_id:
        payload["entity_id"] = entity_id
    if data:
        try:
            payload.update(json.loads(data))
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON data: {data}")
            return
    
    result = http_request("POST", f"/api/services/{domain}/{service}", payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result

def cmd_events():
    """List event types"""
    result = http_request("GET", "/api/events")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result

def main():
    global HA_URL, HA_TOKEN, HEADERS
    
    args = parse_args()
    
    HA_URL = args.url
    HA_TOKEN = args.token
    HEADERS = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    if not args.command:
        print("Usage: ha_bridge.py <command> [options]")
        print("\nCommands:")
        print("  states                     Get all entity states")
        print("  services                   List all services")
        print("  config                     Get HA config")
        print("  state <entity_id>          Get specific entity state")
        print("  call <domain> <service>    Call a service")
        print("  events                     List event types")
        print("\nExamples:")
        print("  python ha_bridge.py states")
        print("  python ha_bridge.py state light.living_room")
        print("  python ha_bridge.py call light turn_on --entity-id light.living_room")
        sys.exit(1)
    
    commands = {
        "states": cmd_states,
        "services": cmd_services,
        "config": cmd_config,
        "state": lambda: cmd_state(args.entity_id),
        "call": lambda: cmd_call(args.domain, args.service, args.entity_id, args.data),
        "events": cmd_events,
    }
    
    if args.command in commands:
        commands[args.command]()
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
