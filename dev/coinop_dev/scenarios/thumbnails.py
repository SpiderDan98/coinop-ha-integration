"""Slicer-like Thumbnails: each part a shaded model in its Material's colour."""

from collections.abc import Callable, Sequence
from functools import cache
from io import BytesIO
import math
import re

import numpy as np
from numpy.typing import ArrayLike, NDArray
from PIL import Image, ImageDraw, ImageFilter

# Triangles, shape (n, 3, 3).
Mesh = NDArray[np.float64]

WIDTH, HEIGHT, SUPERSAMPLE = 640, 480, 2


def _unit(vector: ArrayLike) -> NDArray[np.float64]:
    array = np.asarray(vector, float)
    array /= np.linalg.norm(array)
    return array


EYE = _unit((0.6, -1.0, 0.85))
RIGHT = _unit(np.cross((0, 0, 1), EYE))
UP = np.cross(EYE, RIGHT)
KEY = _unit((-0.5, -0.9, 1.3))
FILL = _unit((1.0, -0.1, 0.25))
HALF = _unit(KEY + EYE)


# Shapes


def join(*meshes: Mesh) -> Mesh:
    return np.concatenate(meshes)


def move(mesh: Mesh, x: float = 0, y: float = 0, z: float = 0) -> Mesh:
    moved: Mesh = mesh + np.array((x, y, z))
    return moved


def turn(mesh: Mesh, axis: str, degrees: float) -> Mesh:
    i, j = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}[axis]
    cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    turned = mesh.copy()
    turned[..., i] = cos * mesh[..., i] - sin * mesh[..., j]
    turned[..., j] = sin * mesh[..., i] + cos * mesh[..., j]
    return turned


def _band(a: NDArray[np.float64], b: NDArray[np.float64]) -> Mesh:
    """The quads between two closed loops of as many points."""
    a2, b2 = np.roll(a, -1, axis=0), np.roll(b, -1, axis=0)
    return np.concatenate([np.stack([a, b, b2], 1), np.stack([a, b2, a2], 1)])


def _lift(outline: NDArray[np.float64], z: float) -> NDArray[np.float64]:
    return np.column_stack([outline, np.full(len(outline), z)])


def _ears(outline: NDArray[np.float64]) -> list[tuple[int, int, int]]:
    """Ear clipping of a simple polygon, concave or not."""

    def cross(a: int, b: int, c: int) -> float:
        (ax, ay), (bx, by), (cx, cy) = outline[a], outline[b], outline[c]
        return float((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))

    order = list(range(len(outline)))
    x, y = outline.T
    if np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y) < 0:
        order.reverse()
    triangles = []
    while len(order) > 3:
        for k in range(len(order)):
            a, b, c = order[k - 1], order[k], order[(k + 1) % len(order)]
            if cross(a, b, c) <= 1e-9:
                continue
            if any(
                cross(a, b, m) > 0 and cross(b, c, m) > 0 and cross(c, a, m) > 0
                for m in order
                if m not in (a, b, c)
            ):
                continue
            triangles.append((a, b, c))
            del order[k]
            break
        else:
            break
    triangles += [(order[0], order[k], order[k + 1]) for k in range(1, len(order) - 1)]
    return triangles


def prism(outline: Sequence[tuple[float, float]], z0: float, z1: float) -> Mesh:
    """A polygon in the xy-plane, extruded from z0 to z1."""
    points = np.asarray(outline, float)
    # A point repeated where an arc meets a line is never an ear.
    points = points[np.any(points != np.roll(points, 1, axis=0), axis=1)]
    bottom, top = _lift(points, z0), _lift(points, z1)
    caps = [
        [cap[a], cap[b], cap[c]] for cap in (bottom, top) for a, b, c in _ears(points)
    ]
    return join(np.array(caps), _band(bottom, top))


def ring(
    outer: Sequence[tuple[float, float]],
    inner: Sequence[tuple[float, float]],
    z0: float,
    z1: float,
) -> Mesh:
    """A wall between two outlines of as many points, from z0 to z1."""
    o, i = np.asarray(outer, float), np.asarray(inner, float)
    o0, o1, i0, i1 = _lift(o, z0), _lift(o, z1), _lift(i, z0), _lift(i, z1)
    return join(_band(o0, o1), _band(i0, i1), _band(o1, i1), _band(o0, i0))


def slab(
    outline: Sequence[tuple[float, float]], width: float, along: str = "y"
) -> Mesh:
    """A side view (horizontal, z), `width` thick along y, or along x."""
    upright = turn(prism(outline, -width / 2, width / 2), "x", 90)
    return upright if along == "y" else turn(upright, "z", 90)


def lathe(
    profile: Sequence[tuple[float, float]],
    segments: int = 64,
    shape: Callable[[NDArray[np.float64], NDArray[np.float64]], NDArray[np.float64]]
    | None = None,
) -> Mesh:
    """A closed (radius, z) profile turned around the z-axis; `shape(angle, z)`
    scales the radius."""
    points = np.asarray(profile, float)
    angle = np.linspace(0, 2 * math.pi, segments + 1)[:, None]
    radius, z = points[:, 0][None, :], points[:, 1][None, :]
    if shape is not None:
        radius = radius * shape(angle, z)
    grid = np.stack(
        np.broadcast_arrays(radius * np.cos(angle), radius * np.sin(angle), z), -1
    )
    a, b = grid[:-1], grid[1:]
    a2, b2 = np.roll(a, -1, axis=1), np.roll(b, -1, axis=1)
    quads: Mesh = np.concatenate([np.stack([a, b, b2], 2), np.stack([a, b2, a2], 2)])
    return quads.reshape(-1, 3, 3)


def box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> Mesh:
    return prism([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1)


def cylinder(radius: float, z0: float, z1: float, segments: int = 48) -> Mesh:
    return lathe([(0, z0), (radius, z0), (radius, z1), (0, z1)], segments)


def tube(outer: float, inner: float, z0: float, z1: float, segments: int = 48) -> Mesh:
    return lathe([(inner, z0), (outer, z0), (outer, z1), (inner, z1)], segments)


def arc(
    radius: float,
    start: float,
    end: float,
    steps: int = 16,
    centre: tuple[float, float] = (0, 0),
) -> list[tuple[float, float]]:
    return [
        (centre[0] + radius * math.cos(t), centre[1] + radius * math.sin(t))
        for t in np.radians(np.linspace(start, end, steps))
    ]


def rounded(
    width: float, depth: float, radius: float, steps: int = 6
) -> list[tuple[float, float]]:
    radius = max(radius, 0.5)
    x, y = width / 2 - radius, depth / 2 - radius
    corners = [(x, y), (-x, y), (-x, -y), (x, -y)]
    return [
        point
        for k, centre in enumerate(corners)
        for point in arc(radius, 90 * k, 90 * (k + 1), steps, centre)
    ]


def tray(width: float, depth: float, height: float, wall: float, radius: float) -> Mesh:
    outline = rounded(width, depth, radius)
    inside = rounded(width - 2 * wall, depth - 2 * wall, radius - wall)
    return join(prism(outline, 0, wall), ring(outline, inside, wall, height))


# Models, in mm on the build plate.


def cable_holder() -> Mesh:
    top = []
    for centre in (22.5, 7.5, -7.5, -22.5):
        top += [(centre + 4, 24), *arc(4, 0, -180, 9, (centre, 14)), (centre - 4, 24)]
    return slab([(-32, 0), (32, 0), (32, 24), *top, (-32, 24)], 26)


def enclosure() -> Mesh:
    case = tray(66, 46, 30, 2.4, 5)
    posts = [move(tube(3.2, 1.4, 2, 24), x, y) for x in (-27, 27) for y in (-17, 17)]
    lid = join(
        prism(rounded(66, 46, 5), 0, 2.4),
        ring(rounded(61, 41, 3), rounded(58, 38, 2), 2.4, 6),
    )
    return join(move(join(case, *posts), x=-38), move(lid, x=38))


def plant_pot() -> Mesh:
    ribs = lambda angle, z: 1 + 0.018 * np.cos(28 * angle) * (z > 8) * (z < 70)  # noqa: E731
    pot = lathe(
        [(0, 0), (38, 0), (50, 70), (54, 70), (54, 76), (48, 76), (35.5, 4), (0, 4)],
        112,
        ribs,
    )
    saucer = lathe([(0, 0), (58, 0), (62, 9), (59, 9), (56, 3), (0, 3)], 112)
    return join(saucer, move(pot, z=3))


def camera_mount() -> Mesh:
    ball = lathe(arc(11, -90, 90, 17, (0, 51)), 48)
    mount = join(
        prism(rounded(44, 34, 6), 0, 5),
        box(-5, -6, 5, 5, 6, 34),
        cylinder(5, 30, 42),
        ball,
    )
    socket = join(tube(14, 11.2, 0, 14), box(13, -4, 0, 22, 4, 14))
    return join(mount, move(socket, x=42, y=6))


def wheels() -> Mesh:
    wheel = lathe(
        [
            (3, 0),
            (8, 0),
            (8, 5),
            (20, 5),
            (20, 1),
            (24, 1),
            (24, 13),
            (20, 13),
            (20, 9),
            (8, 9),
            (8, 14),
            (3, 14),
        ],
        56,
    )
    return join(*(move(wheel, x, y) for x in (-27, 27) for y in (-27, 27)))


def headphone_stand() -> Mesh:
    saddle = slab(
        [*arc(34, 15, 165, 24, (0, 112)), *arc(27, 165, 15, 24, (0, 112))], 38
    )
    return join(
        lathe([(0, 0), (46, 0), (46, 4), (38, 10), (0, 10)], 96),
        cylinder(9, 10, 141),
        lathe([(0, 128), (16, 128), (9, 136), (0, 136)], 48),
        saddle,
    )


def drawer_organiser() -> Mesh:
    return join(
        tray(124, 84, 32, 2, 5),
        box(-61, 7, 0, 61, 9, 30),
        box(-21, -41, 0, -19, 8, 30),
        box(19, -41, 0, 21, 8, 30),
        box(-1, 8, 0, 1, 41, 30),
    )


def phone_stand() -> Mesh:
    return join(
        slab([(-42, 0), (30, 0), (30, 6), (-42, 6)], 72, along="x"),
        slab([(-42, 0), (-34, 0), (-34, 18), (-42, 18)], 72, along="x"),
        slab([(-26, 0), (-16, 0), (14, 96), (6, 96)], 64, along="x"),
        slab([(18, 0), (28, 0), (4, 62), (-4, 56)], 56, along="x"),
    )


def pi_case() -> Mesh:
    case = join(tray(92, 63, 24, 2, 6), box(-46.5, -12, 6, -44, 12, 16))
    vents = [box(-30, y, 2.5, 30, y + 3, 4) for y in range(-20, 21, 8)]
    lid = join(
        prism(rounded(92, 63, 6), 0, 2.5),
        ring(rounded(86, 57, 4), rounded(83, 54, 3), 2.5, 6),
        *vents,
    )
    return join(move(case, y=-36), move(lid, y=36))


def wall_hook() -> Mesh:
    profile = [
        (6, 0),
        (6, 72),
        *arc(3, 0, 180, 8, (3, 72)),
        (0, 8),
        (-30, 8),
        *arc(3.5, 0, 180, 8, (-33.5, 24)),
        (-37, 4),
        *arc(4, 180, 270, 6, (-33, 4)),
        (2, 0),
    ]
    return join(slab(profile, 22), slab([(6, 40), (14, 40), (14, 60), (6, 60)], 16))


def lamp_shade() -> Mesh:
    heights = np.linspace(0, 1, 14)
    outer = [(36 + 34 * (1 - h) ** 1.6, 95 * h) for h in heights]
    inner = [(r - 1.6, z) for r, z in reversed(outer)]
    ribs = lambda angle, z: 1 + 0.025 * np.abs(np.cos(9 * angle))  # noqa: E731
    shade = lathe([*outer, *inner], 144, ribs)
    hub = join(
        tube(20, 15, 88, 95),
        *(turn(box(18, -2, 91, 36, 2, 95), "z", a) for a in (0, 120, 240)),
    )
    return join(shade, hub)


def gridfinity_bins() -> Mesh:
    def bin_(divided: bool) -> Mesh:
        foot = prism(rounded(36, 36, 3), 0, 4)
        walls = move(tray(41.5, 41.5, 26, 1.2, 4), z=4)
        lip = ring(rounded(41.5, 41.5, 4), rounded(37, 37, 2), 28, 30.5)
        label = box(-19.5, 10, 18, 19.5, 19.5, 20)
        divider = [box(-1, -19.5, 4, 1, 19.5, 26)] if divided else []
        return join(foot, walls, lip, label, *divider)

    return join(
        *(
            move(bin_((col + row) % 2 == 0), 44 * col, 44 * row)
            for col in (-1, 0, 1)
            for row in (-0.5, 0.5)
        )
    )


def filament_clips() -> Mesh:
    clip = join(
        prism([*arc(7, 50, 310, 20), *arc(4.6, 310, 50, 20)], 0, 4),
        prism([(5, -2), (16, -2), *arc(2, -90, 90, 8, (16, 0)), (5, 2)], 0, 4),
    )
    return join(*(move(clip, x, y) for x in (-26, 0, 26) for y in (-12, 12)))


def offset(
    outline: Sequence[tuple[float, float]], distance: float
) -> list[tuple[float, float]]:
    """The outline moved `distance` outwards; for smooth, counter-clockwise outlines."""
    points = np.asarray(outline, float)
    edges = np.roll(points, -1, axis=0) - points
    normals = np.column_stack([edges[:, 1], -edges[:, 0]])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    at_points = normals + np.roll(normals, 1, axis=0)
    at_points /= np.linalg.norm(at_points, axis=1)[:, None]
    return [tuple(p) for p in points + distance * at_points]


def cookie_cutter() -> Mesh:
    angles = np.linspace(0, 2 * math.pi, 240, endpoint=False) + math.pi / 2
    radius = 40 * (1 + 0.2 * np.cos(5 * (angles - math.pi / 2)))
    star = list(zip(radius * np.cos(angles), radius * np.sin(angles), strict=True))
    return join(
        ring(star, offset(star, -1.4), 0, 20),
        ring(offset(star, 4), offset(star, -1.4), 0, 2.4),
    )


def keychains() -> Mesh:
    body = prism([(x + 3, y) for x, y in rounded(44, 26, 7)], 0, 3)
    loop = move(ring(arc(7, 0, 360, 33)[:-1], arc(3.6, 0, 360, 33)[:-1], 0, 3), x=-22)
    border = ring(
        [(x + 3, y) for x, y in rounded(44, 26, 7)],
        [(x + 3, y) for x, y in rounded(38, 20, 4)],
        3,
        4.4,
    )
    heart = prism([(4 + 6 * x, 7 * y) for x, y in _heart()], 3, 4.4)
    tag = join(body, loop, border, heart)
    return join(*(move(turn(tag, "z", 8 * k), 6 * k, 34 * k) for k in (-1, 0, 1)))


def _heart() -> list[tuple[float, float]]:
    t = np.linspace(0, 2 * math.pi, 48, endpoint=False)
    x = np.sin(t) ** 3
    y = (13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)) / 16
    return list(zip(y, -x, strict=True))


def spiral_vase() -> Mesh:
    heights = np.linspace(0, 1, 28)
    outer = [(26 + 16 * math.sin(math.pi * h * 0.9) - 6 * h, 130 * h) for h in heights]
    inner = [(r - 1.2, max(z, 1.2)) for r, z in reversed(outer)]
    twist = lambda angle, z: 1 + 0.09 * np.cos(7 * angle + z / 22)  # noqa: E731
    return lathe([(0, 0), *outer, *inner, (0, 1.2)], 168, twist)


def spool_holder() -> Mesh:
    rod = turn(cylinder(6, -40, 40), "y", 90)
    bearing = turn(tube(14, 6, -5, 5), "y", 90)
    upright = slab(
        [(-12, 5), (12, 5), (8, 52), *arc(8, 0, 180, 10, (0, 52)), (-8, 52)],
        8,
        along="x",
    )
    return join(
        prism(rounded(96, 64, 8), 0, 5),
        move(upright, x=-36),
        move(upright, x=36),
        move(rod, z=58),
        move(bearing, x=-18, z=58),
        move(bearing, x=18, z=58),
    )


def bike_light_mount() -> Mesh:
    clamp = slab([*arc(17, -62, 242, 40, (0, 21)), *arc(13, 242, -62, 40, (0, 21))], 20)
    return join(
        clamp,
        box(4, -10, 0, 11, 10, 9),
        box(-11, -10, 0, -4, 10, 9),
        box(-12, -10, 34, 12, 10, 42),
        slab([(-8, 42), (8, 42), (11, 48), (-11, 48)], 20),
    )


def fan_duct() -> Mesh:
    shroud = lathe([(16, 0), (21, 0), (30, 10), (30, 16), (18, 16), (14, 5)], 96)
    inlet = move(ring(rounded(26, 26, 3), rounded(22, 22, 1.5), 10, 40), x=42)
    neck = box(26, -11, 10, 30, 11, 16)
    plate = move(ring(rounded(42, 42, 4), arc(16, -45, 315, 24), 40, 43), x=42)
    return join(shroud, inlet, neck, plate)


def board_game_insert() -> Mesh:
    tokens = [move(tube(13, 11.5, 0, 14), x, -22) for x in (16, 48)]
    return join(
        tray(146, 96, 24, 2, 4),
        box(-2, -47, 0, 0, 47, 22),
        box(0, -2, 0, 72, 0, 22),
        box(-72, 16, 0, -2, 18, 22),
        box(-38, -47, 0, -36, 16, 22),
        *tokens,
    )


def cube() -> Mesh:
    return join(prism(rounded(40, 40, 3), 0, 38), prism(rounded(34, 34, 2), 38, 40))


MODELS: dict[str, Callable[[], Mesh]] = {
    "Desk cable holder": cable_holder,
    "Sensor box enclosure": enclosure,
    "Plant pot": plant_pot,
    "Camera mount": camera_mount,
    "Dishwasher spare part": wheels,
    "Headphone stand": headphone_stand,
    "Drawer organiser": drawer_organiser,
    "Phone stand": phone_stand,
    "Raspberry Pi case": pi_case,
    "Wall hook": wall_hook,
    "Lamp shade": lamp_shade,
    "Gridfinity bins": gridfinity_bins,
    "Filament clip": filament_clips,
    "Cookie cutter": cookie_cutter,
    "Keychain": keychains,
    "Spiral vase": spiral_vase,
    "Spool holder": spool_holder,
    "Bike light mount": bike_light_mount,
    "Fan duct": fan_duct,
    "Board game insert": board_game_insert,
}


# Rendering


def _blur(image: NDArray[np.float64], radius: int) -> NDArray[np.float64]:
    for axis in (0, 1):
        pad = [(radius + 1, radius) if a == axis else (0, 0) for a in (0, 1)]
        summed = np.cumsum(np.pad(image, pad, mode="edge"), axis=axis)
        image = (
            np.take(summed, range(2 * radius + 1, summed.shape[axis]), axis=axis)
            - np.take(summed, range(summed.shape[axis] - 2 * radius - 1), axis=axis)
        ) / (2 * radius + 1)
    return image


@cache
def _layers(part: str) -> NDArray[np.uint8]:
    """The part's lighting, highlights, coverage and shadow, at the final size."""
    mesh = MODELS.get(part, cube)()
    width, height = WIDTH * SUPERSAMPLE, HEIGHT * SUPERSAMPLE
    floor = mesh.copy()
    floor[..., 2] = 0
    corners = np.concatenate([mesh, floor]).reshape(-1, 3)
    across, upward = corners @ RIGHT, corners @ UP
    scale = min(width * 0.8 / np.ptp(across), height * 0.78 / np.ptp(upward))
    centre = np.array(
        [(across.max() + across.min()) / 2, (upward.max() + upward.min()) / 2]
    )

    def screen(points: NDArray[np.float64]) -> NDArray[np.float64]:
        flat = np.stack([points @ RIGHT, points @ UP], -1) - centre
        return np.stack(
            [width / 2 + flat[..., 0] * scale, height * 0.52 - flat[..., 1] * scale], -1
        )

    pixels, depths = screen(mesh), (mesh @ EYE) * scale
    depth = np.full((height, width), -np.inf)
    face = np.full((height, width), -1)
    for k, ((x0, y0), (x1, y1), (x2, y2)) in enumerate(pixels):
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        left, right = (
            max(math.floor(min(x0, x1, x2)), 0),
            min(math.ceil(max(x0, x1, x2)), width - 1),
        )
        top, bottom = (
            max(math.floor(min(y0, y1, y2)), 0),
            min(math.ceil(max(y0, y1, y2)), height - 1),
        )
        if left > right or top > bottom:
            continue
        xs, ys = np.meshgrid(
            np.arange(left, right + 1) + 0.5, np.arange(top, bottom + 1) + 0.5
        )
        w0 = ((x1 - xs) * (y2 - ys) - (x2 - xs) * (y1 - ys)) / area
        w1 = ((x2 - xs) * (y0 - ys) - (x0 - xs) * (y2 - ys)) / area
        w2 = 1 - w0 - w1
        d0, d1, d2 = depths[k]
        z = w0 * d0 + w1 * d1 + w2 * d2
        region = depth[top : bottom + 1, left : right + 1]
        closer = (w0 >= 0) & (w1 >= 0) & (w2 >= 0) & (z > region)
        region[closer] = z[closer]
        face[top : bottom + 1, left : right + 1][closer] = k

    normals = np.cross(mesh[:, 1] - mesh[:, 0], mesh[:, 2] - mesh[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1), 1e-12)[:, None]
    # Seen from either side: winding doesn't matter.
    normals *= np.where(normals @ EYE < 0, -1, 1)[:, None]
    light = (
        0.3
        + 0.62 * np.clip(normals @ KEY, 0, None)
        + 0.2 * np.clip(normals @ FILL, 0, None)
    )
    shine = 0.3 * np.clip(normals @ HALF, 0, None) ** 28

    covered = face >= 0
    # Ambient occlusion from the depth: what lies deeper than its surroundings is shaded.
    near = np.where(covered, depth, depth[covered].min())
    hollow = np.clip((_blur(near, 14) - near) / (40 * SUPERSAMPLE), 0, 0.45) * covered
    lit = np.where(covered, light[face] * (1 - hollow), 0)
    glint = np.where(covered, shine[face], 0)

    footprint = Image.new("L", (width, height))
    draw = ImageDraw.Draw(footprint)
    for triangle in screen(floor):
        draw.polygon([tuple(p) for p in triangle], fill=255)
    shadow = footprint.filter(ImageFilter.GaussianBlur(9 * SUPERSAMPLE))

    channels = [
        Image.fromarray(np.clip(channel * 200, 0, 255).astype(np.uint8))
        for channel in (lit, glint * 4, covered.astype(float) * 1.275)
    ] + [shadow]
    small = [c.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS) for c in channels]
    return np.stack([np.asarray(c) for c in small], -1)


def _part(name: str) -> str:
    return re.sub(r" v\d+$", "", name)


def thumbnail(name: str, colour: str) -> bytes:
    """A PNG of the part `name`, printed in `colour`; blocking."""
    layers = _layers(_part(name)).astype(float)
    lit, glint, covered, shadow = (layers[..., k] for k in range(4))
    lit, glint, covered, shadow = lit / 200, glint / 800, covered / 255, shadow / 255
    base = np.array([int(colour[k : k + 2], 16) for k in (1, 3, 5)]) / 255
    # As slicers do, a dark filament is shown a little lighter.
    base = 0.1 + 0.9 * base
    rows = np.linspace(0, 1, HEIGHT)[:, None, None]
    background = (
        np.array([0.95, 0.96, 0.97]) * (1 - rows) + np.array([0.82, 0.84, 0.87]) * rows
    )
    background = background * (1 - 0.28 * shadow[..., None])
    part = base * lit[..., None] + glint[..., None]
    pixels = background * (1 - covered[..., None]) + part
    image = Image.fromarray((np.clip(pixels, 0, 1) * 255).astype(np.uint8))
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()
