(() => {
    const counts = [20, 50, 100, 250];
    const groupSelector = '[class*="NormalButtonGroup_buttonsGroup_"]';
    const openSelector = '[class*="NormalButtonGroup_openButton_"]';
    const buttonSelector = '[class*="CheckButton_base_"]';
    const checkedSelector = '[class*="CheckButton_check_"]';
    const extraButtonSelector = '[data-wotstat-count]';
    let group;
    let row;
    let boxID;
    let selectedCount = 0;

    function currentBox() {
        const model = window.model;
        const item = Array.prototype.find.call(model.lootboxes, item => item.value.boxID === model.currentLootboxID);
        return item && item.value;
    }

    function resetSelection() {
        selectedCount = 0;
        refresh();
    }

    function onOpen(event) {
        if (!selectedCount) return;

        event.stopPropagation();
        const box = currentBox();
        if (box && box.boxID === boxID && box.isOpenEnabled && box.count >= selectedCount &&
                window.model.currentState === 'STORAGE_VIEWING') {
            window.model.openLootBoxes({lootBoxID: boxID, wotstatCount: selectedCount});
        }
    }

    function refresh() {
        const nextGroup = document.querySelector(groupSelector);
        const box = currentBox();
        if (group !== nextGroup || boxID !== window.model.currentLootboxID) {
            if (row) row.style.width = '';
            group = nextGroup;
            row = group && group.closest('[class*="BoxRadioButtons_base_"]');
            boxID = window.model.currentLootboxID;
            selectedCount = 0;
        }
        if (!group || !box) return;

        const stockMax = box.manualMaxOpenCount || 10;
        const extraCounts = counts.filter(count => count > stockMax);
        const stockButtons = Array.from(group.children).filter(button =>
            button.matches(buttonSelector) && !button.hasAttribute('data-wotstat-count'));
        if (!group.querySelector(extraButtonSelector)) {
            const checkedButton = stockButtons.find(button => button.querySelector(checkedSelector));
            if (!checkedButton || stockButtons.length !== 2 || extraCounts.length === 0) return;

            const caption = stockButtons[0].lastElementChild.textContent;
            for (const count of counts) {
                const button = checkedButton.cloneNode(true);
                button.dataset.wotstatCount = String(count);
                button.lastElementChild.lastElementChild.textContent = caption.replace('1', String(count));
                button.addEventListener('click', () => {
                    if (!button.classList.contains('wotstat-disabled')) {
                        selectedCount = count;
                        refresh();
                    }
                });
                group.appendChild(button);
            }
        }

        if (selectedCount > box.count || selectedCount <= stockMax) selectedCount = 0;
        for (const button of stockButtons) {
            button.addEventListener('click', resetSelection);
            button.classList.toggle('wotstat-unselected', selectedCount !== 0);
        }
        const openButton = group.parentElement.querySelector(openSelector);
        if (openButton) openButton.addEventListener('click', onOpen);
        if (row && extraCounts.length) row.style.width = `${363 + extraCounts.length * 98}rem`;

        for (const button of group.querySelectorAll(extraButtonSelector)) {
            const count = Number(button.dataset.wotstatCount);
            button.style.display = count <= stockMax ? 'none' : '';
            button.classList.toggle('wotstat-unselected', count !== selectedCount);
            button.classList.toggle('wotstat-disabled', count > box.count || window.model.currentState !== 'STORAGE_VIEWING');
        }
    }

    engine.whenReady.then(() => {
        if (!window.model || typeof window.model.openLootBoxes !== 'function') return;
        engine.on('viewEnv.onDataChanged', refresh);
        new MutationObserver(refresh).observe(document.getElementById('root'), {childList: true, subtree: true});
        refresh();
    });
})();
