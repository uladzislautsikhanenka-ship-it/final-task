/** @odoo-module **/

import { onMounted, onWillUnmount } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { useService } from "@web/core/utils/hooks";

/**
 * Патч навигации:
 * - добавляет бейдж с количеством записей "на рассмотрении" к пункту меню "Тренировки"
 */
patch(NavBar.prototype, {
    setup() {
        super.setup();
        
        this.orm = useService("orm");
        this.pendingApprovalsBadge = {
            count: 0,
            intervalId: null,
            badgeElement: null,
            menuElement: null
        };
        
        onMounted(() => {
            this.initPendingApprovalsBadge();
        });
        
        onWillUnmount(() => {
            this.cleanupPendingApprovalsBadge();
        });
    },
    
    async initPendingApprovalsBadge() {
        try {
            console.log("[PendingApprovalsBadge] Начинаем инициализацию бейджа");
            const maxAttempts = 10;
            let attempts = 0;
            
            const tryFindMenu = async () => {
                attempts++;
                const trainingMenu = this.findTrainingMenu();
                
                if (trainingMenu) {
                    console.log("[PendingApprovalsBadge] Меню найдено, загружаем количество записей");
                    this.pendingApprovalsBadge.menuElement = trainingMenu;
                    
                    // Загружаем количество записей на рассмотрении
                    await this.updatePendingApprovalsCount();
                    
                    // Обновляем бейдж каждые 30 секунд
                    this.pendingApprovalsBadge.intervalId = setInterval(() => {
                        this.updatePendingApprovalsCount();
                    }, 30000);
                    this.observeTrainingMenuChanges();
                } else if (attempts < maxAttempts) {
                    setTimeout(tryFindMenu, 1000);
                } else {
                    console.log("[PendingApprovalsBadge] Меню 'Тренировки' не найдено после", maxAttempts, "попыток");
                }
            };
            setTimeout(tryFindMenu, 2000);
            
        } catch (error) {
            console.error("[PendingApprovalsBadge] Ошибка при инициализации бейджа:", error);
        }
    },
    
    findTrainingMenu() {
        const navbar = document.querySelector('.o_main_navbar, nav, [class*="NavBar"], [class*="navbar"]');
        if (navbar) {
            const allLinks = navbar.querySelectorAll('a');
            for (const link of allLinks) {
                const text = (link.textContent || link.innerText || '').trim();
                if (text === 'Тренировки' && !link.closest('.dropdown-menu, [class*="dropdown"]')) {
                    return link;
                }
            }
        }
        const menuByXmlId = document.querySelector('[data-menu-xmlid*="menu_tennis_club_management_training"]');
        if (menuByXmlId) {
            return menuByXmlId;
        }

        const links = document.querySelectorAll('a[href*="training"], a[href*="Тренировки"]');
        for (const link of links) {
            const text = (link.textContent || link.innerText || '').trim();
            if (text === 'Тренировки') {
                return link;
            }
        }
        
        return null;
    },
    
    /**
     * Обновляет количество записей на рассмотрении и отображает бейдж
     */
    async updatePendingApprovalsCount() {
        try {
            // Получаем количество записей со статусом draft, которые записаны тренером самому себе
            // Исправляем: используем true (lowercase) вместо True (Python boolean)
            const count = await this.orm.call(
                'training.booking',
                'search_count',
                [[['state', '=', 'draft'], ['is_trainer_self_booking', '=', true]]]
            );
            
            this.pendingApprovalsBadge.count = count || 0;
            console.log("[PendingApprovalsBadge] Найдено записей на рассмотрении:", this.pendingApprovalsBadge.count);
            
            // Обновляем бейдж в DOM
            this.updateBadgeInDOM(this.pendingApprovalsBadge.count);
            
        } catch (error) {
            console.error("[PendingApprovalsBadge] Ошибка при обновлении количества:", error);
            // Если ошибка, скрываем бейдж
            this.pendingApprovalsBadge.count = 0;
            this.updateBadgeInDOM(0);
        }
    },
    
    /**
     * Обновляет бейдж в DOM
     */
    updateBadgeInDOM(count) {
        // Используем сохраненный элемент меню или ищем заново
        let trainingMenu = this.pendingApprovalsBadge.menuElement || this.findTrainingMenu();
        
        if (!trainingMenu) {
            if (count > 0) {
                setTimeout(() => this.updateBadgeInDOM(count), 1000);
            }
            return;
        }
        
        this.pendingApprovalsBadge.menuElement = trainingMenu;
        
        // Находим родительский элемент для позиционирования бейджа
        let menuItem = trainingMenu.closest('li, div[class*="menu"], [class*="MenuItem"], [class*="o_menu"], [role="menuitem"]') || trainingMenu.parentElement;
        if (!menuItem || menuItem === document.body) {
            menuItem = trainingMenu;
        }
        
        // Если количество = 0, скрываем бейдж
        if (count === 0) {
            if (this.pendingApprovalsBadge.badgeElement) {
                this.pendingApprovalsBadge.badgeElement.remove();
                this.pendingApprovalsBadge.badgeElement = null;
            }
            // Убираем визуальные индикаторы
            if (menuItem) {
                menuItem.classList.remove('o_pending_approvals_menu');
            }
            if (trainingMenu) {
                trainingMenu.classList.remove('o_pending_approvals_menu');
            }
            return;
        }
 
        const container = trainingMenu;
        if (!container) {
            return;
        }

        const computedStyle = window.getComputedStyle(container);
        if (computedStyle.position === 'static' || computedStyle.position === '') {
            container.style.position = 'relative';
        }
        container.classList.add('o_pending_approvals_menu');
        if (!this.pendingApprovalsBadge.badgeElement) {
            const badge = document.createElement('span');
            badge.className = 'o_pending_approvals_badge';
            container.appendChild(badge);
            this.pendingApprovalsBadge.badgeElement = badge;
        }

        const badge = this.pendingApprovalsBadge.badgeElement;
        badge.textContent = count > 99 ? '99+' : count.toString();
        if (count < 10) {
            badge.classList.add('single-digit');
        } else {
            badge.classList.remove('single-digit');
        }
    },

    observeTrainingMenuChanges() {
        const observer = new MutationObserver((mutations) => {
            if (this.pendingApprovalsBadge.count > 0) {
                setTimeout(() => {
                    this.updateBadgeInDOM(this.pendingApprovalsBadge.count);
                }, 500);
            }
        });
        
        const navbar = document.querySelector('.o_main_navbar, nav, [class*="NavBar"], [class*="navbar"]');
        if (navbar) {
            observer.observe(navbar, {
                childList: true,
                subtree: true,
                attributes: false
            });
        }
    },
    
    cleanupPendingApprovalsBadge() {
        if (this.pendingApprovalsBadge.intervalId) {
            clearInterval(this.pendingApprovalsBadge.intervalId);
            this.pendingApprovalsBadge.intervalId = null;
        }
        
        if (this.pendingApprovalsBadge.badgeElement) {
            this.pendingApprovalsBadge.badgeElement.remove();
            this.pendingApprovalsBadge.badgeElement = null;
        }
        
        if (this.pendingApprovalsBadge.menuElement) {
            this.pendingApprovalsBadge.menuElement.classList.remove('o_pending_approvals_menu');
        }
    }
});

