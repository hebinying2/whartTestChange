"""APP 控件树解析与定位生成（阶段 4 元素采集）。

来源：adb uiautomator dump / Appium driver.page_source 输出的
UI Automator XML。按方案 9.2 优先级生成推荐定位：
accessibility_id → resource_id → uiautomator → xpath。
"""

import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger('actuator.app_elements')

# 可点击/可交互节点才会进入采集结果，避免控件树爆炸
_INTERACTIVE_ATTRS = ('clickable', 'scrollable', 'long-clickable', 'editable')


def generate_locator(node: dict) -> dict:
    """按优先级生成推荐定位表达式。

    注意：入参是 parse_ui_xml 构建后的 dict（key 为下划线风格），
    不是 XML 原始属性名（content-desc）。
    """
    if node.get('content_desc'):
        return {'locator_type': 'accessibility_id', 'locator_value': node['content_desc']}
    if node.get('resource_id'):
        return {'locator_type': 'resource_id', 'locator_value': node['resource_id']}
    text = (node.get('text') or '').strip()
    if text:
        return {'locator_type': 'uiautomator',
                'locator_value': f'new UiSelector().text("{text}")'}
    if node.get('class') and node.get('bounds'):
        b = node['bounds']
        return {'locator_type': 'xpath',
                'locator_value': (f"//{node['class']}[@bounds='{b}']")}
    return {'locator_type': 'resource_id', 'locator_value': ''}


def parse_bounds(bounds: str) -> dict | None:
    """解析 "[x1,y1][x2,y2]" → {x1,y1,x2,y2,w,h}。"""
    try:
        import re
        nums = [int(n) for n in re.findall(r'-?\d+', bounds)]
        if len(nums) != 4:
            return None
        x1, y1, x2, y2 = nums
        return {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                'w': x2 - x1, 'h': y2 - y1,
                'cx': (x1 + x2) // 2, 'cy': (y1 + y2) // 2}
    except Exception:
        return None


def parse_ui_xml(xml: str) -> list[dict]:
    """解析控件树 XML → 可交互节点列表（扁平，含推荐定位）。

    兼容两种来源格式：
    - adb uiautomator dump：节点标签固定为 <node>
    - Appium page_source：节点标签为控件类名（如 <android.widget.Button>）
    两者属性集一致（text/clickable/bounds/...），按「有 class 属性即节点」遍历。
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise RuntimeError(f'控件树 XML 解析失败: {exc}') from exc

    results: list[dict] = []
    for elem in root.iter():
        if elem.tag == 'hierarchy':
            continue
        attrs = dict(elem.attrib)
        if not attrs.get('class'):
            continue
        interactive = any(attrs.get(k) == 'true' for k in _INTERACTIVE_ATTRS)
        has_text = bool((attrs.get('text') or '').strip())
        if not (interactive or has_text):
            continue
        bounds = parse_bounds(attrs.get('bounds', ''))
        if not bounds or bounds['w'] <= 0 or bounds['h'] <= 0:
            continue
        node = {
            'class': attrs.get('class', ''),
            'package': attrs.get('package', ''),
            'resource_id': attrs.get('resource-id', ''),
            'text': attrs.get('text', ''),
            'content_desc': attrs.get('content-desc', ''),
            'clickable': attrs.get('clickable') == 'true',
            'long_clickable': attrs.get('long-clickable') == 'true',
            'scrollable': attrs.get('scrollable') == 'true',
            'editable': attrs.get('editable') == 'true',
            'bounds': attrs.get('bounds', ''),
            'rect': bounds,
        }
        node.update(generate_locator(node))
        results.append(node)
    logger.info('控件树解析完成: %d 个可交互节点', len(results))
    return results


def find_node_at(nodes: list[dict], x: int, y: int) -> dict | None:
    """按坐标命中节点（取面积最小者，即最内层控件）。"""
    best = None
    best_area = None
    for n in nodes:
        r = n.get('rect') or {}
        if r.get('x1', 1) <= x <= r.get('x2', -1) and r.get('y1', 1) <= y <= r.get('y2', -1):
            area = r['w'] * r['h']
            if best_area is None or area < best_area:
                best, best_area = n, area
    return best
