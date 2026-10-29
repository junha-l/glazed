# Hand-object grasps

For dexterous or robotic grasp projects: the model predicts grasp parameters for a
hand, conditioned on an object. The scene shows the posed hand and the object,
each as a mesh or as points.

## Getting the hand

The model outputs parameters, not geometry: wrist translation and rotation, plus
joint angles (robot hands such as ShadowHand, Allegro or LEAP) or MANO pose and
shape (human hands). Turn them into geometry with the hand model the repo already
uses for its losses or visualization. Search for names like `HandModel`,
`ManoLayer`, `forward_kinematics`, `pytorch_kinematics`, `urdf`, `get_trimesh`, or
`plotly`. Visualization helpers are the best find, since they already return posed
vertices and faces in the object's frame.

Some repos keep a few hundred hand surface points for penetration or contact losses.
They're too sparse to render well. Build the full mesh and use `sample_surface` on
it (10k-20k points) when the hand should appear as points.

## Getting the object

Use the object the model was conditioned on, with that sample's scale and pose.
Grasp datasets often store a per-grasp object scale (DexGraspNet-style records
carry one), and a grasp only fits the identically scaled object.

## Checking alignment

```python
check_alignment(sample_surface(hand_v, hand_f, 5000), sample_surface(obj_v, obj_f, 20000),
                names=("hand", "object"))
```

- A human or robot hand spans roughly 0.15-0.25 m. If the hand comes out around
  150-250 instead, the data is in millimeters; an object 1000x off from the hand
  points the same way.
- For a contact grasp, the gap should be within a few millimeters (zero or slightly
  negative contact can still print a small positive gap). A gap of several
  centimeters or more usually means the hand is in a different frame from the
  object, or the object's pose or scale wasn't applied.

## Colors and values

- Object `#c9ccd1` (gray). Hand `#e0a96d` (warm) for human hands, `#4c78a8` (blue)
  for robot hands.
- Predicted vs ground-truth hand on one object: `#4c78a8` vs `#e45756`.
- Contact maps: save the object as points with the contact value per point, the hand
  as a solid-colored mesh, and render with `--cmap Reds --vmin 0 --vmax 1`.

```python
gap = closest_distance(obj_points, hand_points)          # e.g. via a KD-tree or torch.cdist
save_points(out / "object.npy", obj_points, values=np.exp(-gap / 0.005))
save_mesh(out / "hand.ply", hand_v, hand_f)
write_scene(out / "scene.toml", [{"path": out / "object.npy"},
                                 {"path": out / "hand.ply", "color": "#4c78a8"}])
```

## Views and layouts

- Choose a view where the fingers are visible rather than hidden behind the object.
  Preview two or three azimuths first.
- Several grasps of one object: one scene per grasp for paper panels, or one scene
  with `grid_locations` when the scale must match exactly. Give the hand and object
  of each grasp the same `location`.
- Overlaying several hands on one object works (several hand entries, one object
  entry), but becomes hard to read beyond two or three.
