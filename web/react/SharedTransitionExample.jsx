/**
 * SharedTransitionExample
 * React example component demonstrating the useSharedTransition hook
 * 
 * This shows a mock launcher UI with:
 * - Sidebar navigation with active indicator
 * - Header with crossfading title
 * - Content panels with fade transitions
 */

import React, { useState, useRef, useCallback } from 'react';
import { useSharedTransition } from './useSharedTransition';
import '../shared-transition-tokens.css';

// Panel data
const PANELS = [
    { id: 'home', icon: '🏠', title: 'Home' },
    { id: 'games', icon: '🎮', title: 'Games Library' },
    { id: 'settings', icon: '⚙️', title: 'Settings' },
    { id: 'about', icon: 'ℹ️', title: 'About' }
];

// Inline styles (in production, use CSS modules or styled-components)
const styles = {
    app: {
        display: 'grid',
        gridTemplateColumns: '64px 1fr',
        gridTemplateRows: '56px 1fr',
        height: '100vh',
        background: '#0a0a0a',
        color: '#fff',
        fontFamily: "'Segoe UI', -apple-system, sans-serif"
    },
    sidebar: {
        gridRow: '1 / -1',
        background: '#111',
        borderRight: '1px solid #222',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '16px 0',
        position: 'relative'
    },
    indicator: {
        position: 'absolute',
        left: 10,
        width: 44,
        height: 44,
        background: 'rgba(255, 102, 0, 0.15)',
        borderRadius: 12,
        border: '1px solid rgba(255, 102, 0, 0.4)',
        pointerEvents: 'none',
        zIndex: 1
    },
    navButton: {
        width: 44,
        height: 44,
        borderRadius: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: 8,
        cursor: 'pointer',
        background: 'transparent',
        border: 'none',
        color: '#666',
        fontSize: 20,
        position: 'relative',
        zIndex: 2,
        transition: 'color 180ms ease, background 180ms ease'
    },
    navButtonActive: {
        color: '#ff6600'
    },
    header: {
        background: '#111',
        borderBottom: '1px solid #222',
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        position: 'relative'
    },
    headerTitle: {
        fontSize: 18,
        fontWeight: 600
    },
    content: {
        background: '#0a0a0a',
        overflow: 'auto',
        position: 'relative'
    },
    panel: {
        position: 'absolute',
        inset: 0,
        padding: 32
    },
    panelHidden: {
        display: 'none'
    },
    panelTitle: {
        fontSize: 28,
        marginBottom: 16,
        color: '#ff6600'
    },
    panelText: {
        color: '#888',
        lineHeight: 1.6,
        maxWidth: 600
    }
};

export function SharedTransitionExample() {
    const [currentPanel, setCurrentPanel] = useState('home');
    const [headerTitle, setHeaderTitle] = useState('Home');

    // Refs for sidebar buttons (to measure target positions)
    const buttonRefs = useRef({});

    // Initialize shared transition hook
    const {
        registerElement,
        getElement,
        animateTransform,
        fadeOut,
        fadeIn,
        isTransitioning,
        cancelAll,
        prefersReducedMotion
    } = useSharedTransition({
        onStart: () => console.log('[React] Transition started'),
        onComplete: () => console.log('[React] Transition complete')
    });

    // Handle navigation click
    const handleNavClick = useCallback(async (targetId) => {
        // Skip if already on this panel or transitioning
        if (targetId === currentPanel) return;

        // Cancel any in-progress transition
        if (isTransitioning) {
            cancelAll();
        }

        const targetButton = buttonRefs.current[targetId];
        const indicator = getElement('indicator');
        const oldPanel = getElement(`panel-${currentPanel}`);
        const newPanel = getElement(`panel-${targetId}`);

        if (!targetButton || !indicator) return;

        // Measure positions
        const indicatorRect = indicator.getBoundingClientRect();
        const buttonRect = targetButton.getBoundingClientRect();
        const sidebarRect = targetButton.parentElement.getBoundingClientRect();

        // Calculate target top position relative to sidebar
        const targetTop = buttonRect.top - sidebarRect.top;

        // Phase 1: Move indicator + fade out old panel (parallel)
        const indicatorPromise = animateTransform(
            indicator,
            indicatorRect,
            { ...buttonRect, top: sidebarRect.top + targetTop, left: sidebarRect.left + 10 }
        );

        const fadeOutPromise = fadeOut(oldPanel);

        await Promise.all([indicatorPromise, fadeOutPromise]);

        // Update indicator position
        indicator.style.top = `${targetTop}px`;

        // Phase 2: State update (triggers re-render)
        setCurrentPanel(targetId);
        setHeaderTitle(PANELS.find(p => p.id === targetId)?.title || targetId);

        // Phase 3: Fade in new panel (after state update)
        // Use requestAnimationFrame to ensure DOM has updated
        requestAnimationFrame(async () => {
            const updatedNewPanel = getElement(`panel-${targetId}`);
            if (updatedNewPanel) {
                updatedNewPanel.style.opacity = '0';
                updatedNewPanel.style.display = 'block';
                await fadeIn(updatedNewPanel);
            }
        });

    }, [currentPanel, isTransitioning, cancelAll, getElement, animateTransform, fadeOut, fadeIn]);

    return (
        <div style={styles.app}>
            {/* SIDEBAR */}
            <nav style={styles.sidebar}>
                <div
                    ref={registerElement('indicator')}
                    style={{ ...styles.indicator, top: 16 }}
                />

                {PANELS.map((panel) => (
                    <button
                        key={panel.id}
                        ref={(el) => { buttonRefs.current[panel.id] = el; }}
                        style={{
                            ...styles.navButton,
                            ...(currentPanel === panel.id ? styles.navButtonActive : {})
                        }}
                        onClick={() => handleNavClick(panel.id)}
                        aria-label={panel.title}
                        aria-current={currentPanel === panel.id ? 'page' : undefined}
                    >
                        {panel.icon}
                    </button>
                ))}
            </nav>

            {/* HEADER */}
            <header style={styles.header}>
                <span style={styles.headerTitle}>{headerTitle}</span>
            </header>

            {/* CONTENT */}
            <main style={styles.content}>
                {PANELS.map((panel) => (
                    <section
                        key={panel.id}
                        ref={registerElement(`panel-${panel.id}`)}
                        style={{
                            ...styles.panel,
                            ...(currentPanel !== panel.id ? styles.panelHidden : {})
                        }}
                    >
                        <h2 style={styles.panelTitle}>{panel.title}</h2>
                        <p style={styles.panelText}>
                            {panel.id === 'home' && 'Welcome to TDD Launcher. Click sidebar icons to see smooth transitions.'}
                            {panel.id === 'games' && 'Your games library with smooth entrance animations.'}
                            {panel.id === 'settings' && 'Configure launcher preferences. Respects prefers-reduced-motion.'}
                            {panel.id === 'about' && 'TDD Launcher v0.9 Beta — React Shared Element Transition Demo.'}
                        </p>
                    </section>
                ))}
            </main>

            {/* Status indicator */}
            <div style={{
                position: 'fixed',
                bottom: 16,
                right: 16,
                background: '#1a1a1a',
                border: '1px solid #333',
                borderRadius: 8,
                padding: '12px 16px',
                fontSize: 13,
                color: '#666'
            }}>
                Motion: <code style={{ background: '#252525', padding: '2px 6px', borderRadius: 4, color: '#ff6600' }}>
                    {prefersReducedMotion ? 'Reduced' : 'Full'}
                </code>
            </div>
        </div>
    );
}

export default SharedTransitionExample;
