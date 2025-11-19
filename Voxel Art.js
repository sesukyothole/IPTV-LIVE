<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Voxel Eagle</title>
    <style>
        body { margin: 0; overflow: hidden; background-color: #87CEEB; }
        canvas { display: block; }
        #loading {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            font-family: monospace; color: white; font-size: 24px; pointer-events: none;
        }
    </style>
</head>
<body>
    <div id="loading">Rendering Voxel Art...</div>
    
    <!-- Import Map for Three.js -->
    <script type="importmap">
        {
            "imports": {
                "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
                "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
            }
        }
    </script>

    <script type="module">
        import * as THREE from 'three';
        import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

        // --- Configuration ---
        const PALETTE = {
            FEATHER_DARK: 0x3E2723,  // Dark Brown
            FEATHER_LIGHT: 0x5D4037, // Medium Brown
            HEAD_WHITE: 0xF5F5F5,    // White
            BEAK: 0xFFC107,          // Yellow/Orange
            EYE: 0x212121,           // Black
            WOOD: 0x4E342E,          // Branch
            LEAF: 0x4CAF50,          // Green
            SKY: 0x87CEEB            // Sky Blue
        };

        let scene, camera, renderer, controls;
        const voxelSize = 1;
        const gap = 0.02; // Slight gap between blocks for style

        init();
        animate();

        function init() {
            // 1. Scene Setup
            scene = new THREE.Scene();
            scene.background = new THREE.Color(PALETTE.SKY);
            scene.fog = new THREE.Fog(PALETTE.SKY, 20, 80);

            // 2. Camera
            camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
            camera.position.set(20, 15, 25);

            // 3. Renderer
            renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.shadowMap.enabled = true;
            renderer.shadowMap.type = THREE.PCFSoftShadowMap;
            document.body.appendChild(renderer.domElement);

            // 4. Lighting
            const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
            scene.add(ambientLight);

            const dirLight = new THREE.DirectionalLight(0xffffff, 1.5);
            dirLight.position.set(10, 20, 10);
            dirLight.castShadow = true;
            dirLight.shadow.mapSize.width = 2048;
            dirLight.shadow.mapSize.height = 2048;
            scene.add(dirLight);

            // Backlight for rim lighting
            const backLight = new THREE.DirectionalLight(0xffffff, 0.3);
            backLight.position.set(-10, 10, -10);
            scene.add(backLight);

            // 5. Controls
            controls = new OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.autoRotate = true;
            controls.autoRotateSpeed = 1.0;
            controls.target.set(0, 4, 0);

            // 6. Build the Scene
            buildScene();

            // Hide loading text
            document.getElementById('loading').style.display = 'none';

            // Resize handler
            window.addEventListener('resize', onWindowResize);
        }

        // --- Voxel Building Logic ---

        const geometry = new THREE.BoxGeometry(voxelSize - gap, voxelSize - gap, voxelSize - gap);

        function createVoxel(x, y, z, color, parentGroup) {
            const material = new THREE.MeshStandardMaterial({ 
                color: color,
                roughness: 0.8,
                metalness: 0.1
            });
            const cube = new THREE.Mesh(geometry, material);
            cube.position.set(x, y, z);
            cube.castShadow = true;
            cube.receiveShadow = true;
            parentGroup.add(cube);
        }

        function buildScene() {
            const eagleGroup = new THREE.Group();
            scene.add(eagleGroup);

            buildBranch(eagleGroup);
            buildEagle(eagleGroup);
        }

        function buildBranch(group) {
            // Main branch log
            for(let x = -10; x <= 10; x++) {
                // Create a slightly jagged line
                let yOff = Math.sin(x * 0.5) * 0.5; 
                let zOff = Math.cos(x * 0.3) * 0.3;
                
                createVoxel(x, yOff, zOff, PALETTE.WOOD, group);
                
                // Add thickness randomly
                if(x % 2 === 0) createVoxel(x, yOff - 1, zOff, PALETTE.WOOD, group);
                if(Math.random() > 0.7) createVoxel(x, yOff, zOff + 1, PALETTE.WOOD, group);
            }

            // Leaves at the ends
            const leafClusters = [-10, 10];
            leafClusters.forEach(xBase => {
                for(let i=0; i<15; i++) {
                    let x = xBase + (Math.random() * 3 - 1.5);
                    let y = (Math.random() * 3 - 1.5);
                    let z = (Math.random() * 3 - 1.5);
                    createVoxel(x, y, z, PALETTE.LEAF, group);
                }
            });
        }

        function buildEagle(group) {
            const centerX = 0;
            const startY = 1; // On top of branch
            const centerZ = 0;

            // --- TALONS (Yellow) ---
            createVoxel(centerX - 1, startY, centerZ + 1, PALETTE.BEAK, group);
            createVoxel(centerX + 1, startY, centerZ + 1, PALETTE.BEAK, group);

            // --- BODY (Dark & Light Brown) ---
            // Lower Body
            for(let y = 1; y <= 3; y++) {
                for(let x = -2; x <= 2; x++) {
                    for(let z = -1; z <= 2; z++) {
                        // Round the corners slightly by skipping corners
                        if (Math.abs(x) === 2 && Math.abs(z) === 2) continue; 
                        createVoxel(centerX + x, startY + y, centerZ + z, PALETTE.FEATHER_LIGHT, group);
                    }
                }
            }

            // Upper Body / Chest
            for(let y = 4; y <= 6; y++) {
                for(let x = -2; x <= 2; x++) {
                    for(let z = -1; z <= 2; z++) {
                         // Tapering in
                        if (Math.abs(x) === 2 && z < 0) continue;
                        createVoxel(centerX + x, startY + y, centerZ + z, PALETTE.FEATHER_DARK, group);
                    }
                }
            }

            // --- WINGS (Dark Brown) ---
            // Folded wings on the sides
            for(let y = 2; y <= 5; y++) {
                // Left Wing
                createVoxel(centerX - 3, startY + y, centerZ, PALETTE.FEATHER_DARK, group);
                createVoxel(centerX - 3, startY + y, centerZ + 1, PALETTE.FEATHER_DARK, group);
                // Right Wing
                createVoxel(centerX + 3, startY + y, centerZ, PALETTE.FEATHER_DARK, group);
                createVoxel(centerX + 3, startY + y, centerZ + 1, PALETTE.FEATHER_DARK, group);
            }
            // Wing tips extending back
            createVoxel(centerX - 3, startY + 2, centerZ - 1, PALETTE.FEATHER_DARK, group);
            createVoxel(centerX + 3, startY + 2, centerZ - 1, PALETTE.FEATHER_DARK, group);

            // --- TAIL (Dark Brown) ---
            for(let y = 0; y >= -2; y--) {
                for(let x = -1; x <= 1; x++) {
                    createVoxel(centerX + x, startY + y, centerZ - 2, PALETTE.FEATHER_DARK, group);
                }
            }

            // --- HEAD (White) ---
            const neckY = startY + 7;
            // Neck connection
            for(let x = -1; x <= 1; x++) {
                for(let z = -1; z <= 1; z++) {
                    createVoxel(centerX + x, neckY, centerZ + z, PALETTE.HEAD_WHITE, group);
                }
            }
            
            // Main Head Block
            for(let y = 1; y <= 2; y++) {
                for(let x = -1; x <= 1; x++) {
                    for(let z = -1; z <= 2; z++) {
                        createVoxel(centerX + x, neckY + y, centerZ + z, PALETTE.HEAD_WHITE, group);
                    }
                }
            }

            // --- FACE DETAILS ---
            const faceY = neckY + 1;
            
            // Beak (Yellow) - Hook shape
            createVoxel(centerX, faceY, centerZ + 3, PALETTE.BEAK, group); 
            createVoxel(centerX, faceY - 1, centerZ + 3, PALETTE.BEAK, group);
            createVoxel(centerX, faceY - 1, centerZ + 2, PALETTE.BEAK, group);

            // Eyes (Black) - Inset into the white head
            // Right Eye
            createVoxel(centerX + 1.1, faceY + 0.5, centerZ + 1.5, PALETTE.EYE, group).scale.set(0.2, 0.5, 0.5);
            // Left Eye
            createVoxel(centerX - 1.1, faceY + 0.5, centerZ + 1.5, PALETTE.EYE, group).scale.set(0.2, 0.5, 0.5);
            
            // Eyebrows (White overhang)
            createVoxel(centerX + 1, faceY + 1, centerZ + 2, PALETTE.HEAD_WHITE, group);
            createVoxel(centerX - 1, faceY + 1, centerZ + 2, PALETTE.HEAD_WHITE, group);
            createVoxel(centerX, faceY + 1, centerZ + 2, PALETTE.HEAD_WHITE, group);
        }

        function onWindowResize() {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }

        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        }
    </script>
</body>
</html>

