<script setup lang="ts">
import ProfilePlaceholderIcon from "@/assets/img/profile-placeholder.svg?url";
import {useProfileStore} from "@/store/profile";
import {ref, onMounted, useTemplateRef} from "vue";
import Dropdown from "@/components/ui-kit/Dropdown.vue";
import {useDropdown} from "@/components/composables/useDropdown";
import NavLink from "@/components/ui-kit/NavLink.vue";
import {useAuthStore} from "@/store/auth";

const rootEl = useTemplateRef('rootEl')
const { isOpen, toggle } = useDropdown(rootEl);

const profileStore = useProfileStore();
const authStore = useAuthStore()

const name = ref<string>('');
const profilePic = ref<string>(ProfilePlaceholderIcon);

onMounted(async () => {
  const profileData = await profileStore.getProfileData()

  if (!profileData) return

  name.value = profileData.name;
  profilePic.value = profileData.picture;
})
</script>

<template>
<div class="profile-dropdown" ref="rootEl">
  <button class="profile-dropdown__btn"
          type="button"
          @click="toggle"
  >
    <img class="profile-dropdown__img"
         :src="profilePic"
         width="40"
         height="40"
         alt=""
    >
  </button>

  <Dropdown class="profile-dropdown__dropdown"
            v-if="isOpen"
  >
    <div class="profile-dropdown__name-wrapper">
      <span class="profile-dropdown__name">{{ name }}</span>
    </div>
    <div class="profile-dropdown__links">
      <NavLink class="profile-dropdown__link"
               text="My Profile"
               to="/profile"
               right-icon="chevron-right"
      />
      <NavLink class="profile-dropdown__link"
        text="Log Out"
        right-icon="log-out"
        type="error"
               @click = "authStore.logOut"
      />
    </div>
  </Dropdown>
</div>
</template>

<style scoped lang="scss">
.profile-dropdown {
  position: relative;

  &__btn {
    border: none;
    background-color: transparent;
    padding: 0;
    cursor: pointer;
  }

  &__img {
    border-radius: 50%;
    width: 40px;
    height: 40px;
    display: block;
  }

  &__dropdown {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
  }

  &__name-wrapper {
    margin-bottom: 6px;
  }

  &__name {
    font: var(--bold-18);
    white-space: nowrap;
  }

  &__link {
    width: 100%;
  }
}
</style>
