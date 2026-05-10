export const TagRow = {
    name: "TagRow",
    props: {
        tag: {
            type: Object,
            required: true,
        },
        active: {
            type: Boolean,
            default: false,
        },
        favorite: {
            type: Boolean,
            default: false,
        },
    },
    emits: ["select", "toggle-favorite"],
    methods: {
        onKeydown(event) {
            if (event.key !== "Enter" && event.key !== " ") {
                return;
            }
            event.preventDefault();
            this.$emit("select", this.tag);
        },
        onFavoriteClick(event) {
            event.stopPropagation();
            this.$emit("toggle-favorite", this.tag);
        },
    },
    template: `
        <div
            class="tag-row"
            :class="{ active }"
            role="button"
            tabindex="0"
            :aria-selected="active"
            @click="$emit('select', tag)"
            @keydown="onKeydown"
        >
            <div class="tag-row-main">
                <div class="tag-name">{{ tag.name }}</div>
                <div class="tag-row-controls">
                    <div class="tag-meta">
                        <span>{{ tag.category || 'unknown' }}</span>
                        <span>{{ tag.count }}</span>
                    </div>
                    <button
                        class="tag-favorite-toggle"
                        :class="{ 'is-favorite': favorite }"
                        type="button"
                        :aria-label="favorite ? 'Remove favorite' : 'Add favorite'"
                        @click="onFavoriteClick"
                    >
                        {{ favorite ? '*' : '+' }}
                    </button>
                </div>
            </div>
            <div class="tag-alias">{{ tag.aliases || 'No aliases' }}</div>
        </div>
    `,
};
