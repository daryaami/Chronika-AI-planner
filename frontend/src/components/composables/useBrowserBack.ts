import {useRouter} from "vue-router";

export function useBrowserBack(fallbackRoute: string = "/") {
  const router = useRouter()

  const goBack = () => {
    if (window.history.length > 1) {
      router.back()
      return
    }

    router.push(fallbackRoute)
  }

  return {
    goBack,
  }
}
